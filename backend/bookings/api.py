"""API viewsets and permissions for bookings."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from listings.models import Listing
from listings.services import compute_booking_totals
from notifications import tasks as notification_tasks
from payments.stripe_api import (
    StripePaymentError,
    StripeTransientError,
    create_booking_payment_intents,
    ensure_stripe_customer,
)

from .domain import (
    ACTIVE_BOOKING_STATUSES,
    assert_can_cancel,
    assert_can_complete,
    assert_can_confirm,
    assert_can_confirm_pickup,
    ensure_no_conflict,
    is_pre_payment,
    mark_canceled,
)
from .models import Booking
from .serializers import BookingSerializer

logger = logging.getLogger(__name__)


class IsBookingParticipant(permissions.BasePermission):
    """Allow access only to users tied to the booking."""

    def has_permission(self, request, view) -> bool:
        """Always allow; actual checks happen at object level."""
        return True

    def has_object_permission(self, request, view, obj: Booking) -> bool:
        """Check that the user is the booking owner or renter."""
        user_id = getattr(request.user, "id", None)
        return user_id in (obj.owner_id, obj.renter_id)


class BookingViewSet(viewsets.ModelViewSet):
    """CRUD and state transitions for bookings."""

    serializer_class = BookingSerializer
    permission_classes = (permissions.IsAuthenticated, IsBookingParticipant)

    def get_queryset(self):
        """Restrict bookings to the authenticated participant."""
        user = self.request.user
        if not user.is_authenticated:
            return Booking.objects.none()
        return (
            Booking.objects.select_related("listing", "listing__owner", "owner", "renter")
            .prefetch_related("listing__photos")
            .filter(Q(owner=user) | Q(renter=user))
            .order_by("-created_at")
        )

    def get_object(self):
        """Fetch a single booking and enforce participant permissions."""
        obj = get_object_or_404(
            Booking.objects.select_related(
                "listing", "listing__owner", "owner", "renter"
            ).prefetch_related("listing__photos"),
            pk=self.kwargs["pk"],
        )
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer: BookingSerializer) -> None:
        """Persist a new booking."""
        serializer.save()

    @action(detail=False, methods=["get"], url_path="my")
    def my_bookings(self, request, *args, **kwargs):
        """Return the authenticated user's bookings."""
        return self.list(request, *args, **kwargs)

    @action(detail=False, methods=["get"], url_path="pending-requests-count")
    def pending_requests_count(self, request, *args, **kwargs):
        """Return how many booking requests are awaiting the owner's response."""
        user = request.user
        pending_total = Booking.objects.filter(
            owner=user,
            status=Booking.Status.REQUESTED,
        ).count()
        return Response({"pending_requests": pending_total}, status=status.HTTP_200_OK)

    @action(
        detail=False,
        methods=["get"],
        url_path="availability",
        permission_classes=[permissions.AllowAny],
    )
    def availability(self, request, *args, **kwargs):
        """Return booked [start, end) ranges for a listing."""
        listing_param = request.query_params.get("listing")
        if not listing_param:
            return Response(
                {"detail": "listing query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            listing_id = int(listing_param)
        except (TypeError, ValueError):
            return Response(
                {"detail": "listing must be a valid integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        listing = get_object_or_404(
            Listing.objects.filter(is_active=True),
            pk=listing_id,
        )

        ranges = (
            Booking.objects.filter(
                listing=listing,
                status__in=ACTIVE_BOOKING_STATUSES,
            )
            .order_by("start_date", "end_date")
            .values("start_date", "end_date")
        )
        payload = [
            {
                "start_date": item["start_date"].isoformat(),
                "end_date": item["end_date"].isoformat(),
            }
            for item in ranges
        ]
        return Response(payload, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="confirm")
    def confirm(self, request, *args, **kwargs):
        """Confirm a pending booking (owner-only)."""
        booking: Booking = self.get_object()
        if booking.owner_id != request.user.id:
            return Response(
                {"detail": "Only the listing owner can confirm this booking."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            assert_can_confirm(booking)
            ensure_no_conflict(
                booking.listing,
                booking.start_date,
                booking.end_date,
                exclude_booking_id=booking.id,
            )
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        if not booking.totals or "total_charge" not in booking.totals:
            booking.totals = compute_booking_totals(
                listing=booking.listing,
                start_date=booking.start_date,
                end_date=booking.end_date,
            )

        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=["status", "totals", "updated_at"])
        try:
            notification_tasks.send_booking_status_email.delay(
                booking.renter_id,
                booking.id,
                booking.status,
            )
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_status_email",
                exc_info=True,
            )
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, *args, **kwargs):
        """Cancel a booking (owner or renter)."""
        booking: Booking = self.get_object()
        if request.user.id == booking.owner_id:
            actor = "owner"
        elif request.user.id == booking.renter_id:
            actor = "renter"
        else:
            return Response(
                {"detail": "Only the listing owner or renter can cancel this booking."},
                status=status.HTTP_403_FORBIDDEN,
            )

        reason = (request.data.get("reason") or "").strip()

        try:
            assert_can_cancel(booking, actor=actor)
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        cancel_reason = reason or booking.canceled_reason
        update_fields = [
            "status",
            "canceled_by",
            "canceled_reason",
            "auto_canceled",
            "updated_at",
        ]

        if is_pre_payment(booking):
            mark_canceled(booking, actor=actor, auto=False, reason=cancel_reason)
            booking.save(update_fields=update_fields)
        else:
            # TODO: implement paid/after-deposit cancellation policy with refunds.
            mark_canceled(booking, actor=actor, auto=False, reason=cancel_reason)
            booking.save(update_fields=update_fields)

        if actor == "owner":
            try:
                notification_tasks.send_booking_status_email.delay(
                    booking.renter_id,
                    booking.id,
                    booking.status,
                )
            except Exception:
                logger.info(
                    "notifications: could not queue send_booking_status_email",
                    exc_info=True,
                )
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="complete")
    def complete(self, request, *args, **kwargs):
        """Mark a confirmed booking as completed (owner-only)."""
        booking: Booking = self.get_object()
        if booking.owner_id != request.user.id:
            return Response(
                {"detail": "Only the listing owner can complete this booking."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            assert_can_complete(booking)
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="confirm-pickup")
    def confirm_pickup(self, request, *args, **kwargs):
        """Allow listing owners to confirm pickup once requirements are met."""
        booking: Booking = self.get_object()
        if booking.owner_id != request.user.id:
            return Response(
                {"detail": "Only the listing owner can confirm pickup."},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            assert_can_confirm_pickup(booking)
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        from django.utils import timezone

        booking.pickup_confirmed_at = timezone.now()
        booking.save(update_fields=["pickup_confirmed_at", "updated_at"])
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="pay")
    def pay(self, request, *args, **kwargs):
        """Collect payment for a confirmed booking (renter-only)."""
        booking: Booking = self.get_object()
        if booking.renter_id != request.user.id:
            return Response(
                {"detail": "Only the renter can pay for this booking."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status != Booking.Status.CONFIRMED:
            return Response(
                {"detail": "Booking is not in a payable state."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_method_id = (request.data.get("stripe_payment_method_id") or "").strip()
        provided_customer_id = (request.data.get("stripe_customer_id") or "").strip()
        if not payment_method_id:
            return Response(
                {"detail": "stripe_payment_method_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            customer_id = ensure_stripe_customer(
                request.user,
                customer_id=provided_customer_id or None,
            )
        except StripeTransientError:
            return Response(
                {"detail": "Temporary payment issue, please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripePaymentError as exc:
            message = str(exc) or "Payment could not be completed."
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        try:
            charge_id, deposit_id = create_booking_payment_intents(
                booking=booking,
                customer_id=customer_id,
                payment_method_id=payment_method_id,
            )
        except StripeTransientError:
            return Response(
                {"detail": "Temporary payment issue, please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripePaymentError as exc:
            message = str(exc) or "Payment could not be completed."
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        booking.charge_payment_intent_id = charge_id or ""
        booking.deposit_hold_id = deposit_id or ""
        booking.status = Booking.Status.PAID
        booking.save(
            update_fields=[
                "status",
                "charge_payment_intent_id",
                "deposit_hold_id",
                "updated_at",
            ]
        )
        try:
            notification_tasks.send_booking_payment_receipt_email.delay(
                booking.renter_id,
                booking.id,
            )
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_payment_receipt_email",
                exc_info=True,
            )
        return Response(self.get_serializer(booking).data, status=status.HTTP_200_OK)
