"""API viewsets and permissions for bookings."""

from __future__ import annotations

import logging

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from notifications import tasks as notification_tasks

from .domain import assert_can_cancel, assert_can_complete, assert_can_confirm, ensure_no_conflict
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
            Booking.objects.select_related("listing", "owner", "renter")
            .filter(Q(owner=user) | Q(renter=user))
            .order_by("-created_at")
        )

    def get_object(self):
        """Fetch a single booking and enforce participant permissions."""
        obj = get_object_or_404(
            Booking.objects.select_related("listing", "owner", "renter"),
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

        booking.status = Booking.Status.CONFIRMED
        booking.save(update_fields=["status", "updated_at"])
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
        try:
            assert_can_cancel(booking)
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        booking.status = Booking.Status.CANCELED
        booking.save(update_fields=["status", "updated_at"])
        if booking.owner_id == request.user.id:
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
