"""API viewsets and permissions for bookings."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from chat.models import Message as ChatMessage
from chat.models import create_system_message
from core.redis import push_event
from core.settings_resolver import get_int
from listings.models import Listing
from listings.services import compute_booking_totals
from notifications import tasks as notification_tasks
from payments.ledger import log_transaction
from payments.models import Transaction
from payments.stripe_api import (
    StripeConfigurationError,
    StripePaymentError,
    StripeTransientError,
    capture_deposit_amount,
    create_booking_charge_intent,
    create_late_fee_payment_intent,
    ensure_stripe_customer,
)
from payments_cancellation_policy import compute_refund_amounts
from payments_refunds import apply_cancellation_settlement, get_platform_ledger_user
from storage.s3 import booking_object_key, guess_content_type, presign_put, public_url
from storage.tasks import scan_and_finalize_booking_photo

from .domain import (
    ACTIVE_BOOKING_STATUSES,
    assert_can_cancel,
    assert_can_complete,
    assert_can_confirm,
    assert_can_confirm_pickup,
    ensure_no_conflict,
    extra_days_for_late,
    is_pre_payment,
    is_severely_overdue,
    mark_canceled,
)
from .models import Booking, BookingPhoto
from .serializers import BookingSerializer

logger = logging.getLogger(__name__)
_CENT = Decimal("0.01")


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _decimal_from_value(value: object, default: str | Decimal = "0") -> Decimal:
    if isinstance(value, Decimal):
        candidate = value
    else:
        try:
            candidate = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            candidate = Decimal(str(default))
    return _quantize_money(candidate)


def _ensure_booking_totals(booking: Booking) -> dict[str, str]:
    totals = booking.totals or {}
    if "rental_subtotal" not in totals:
        totals = compute_booking_totals(
            listing=booking.listing,
            start_date=booking.start_date,
            end_date=booking.end_date,
        )
        booking.totals = totals
        booking.save(update_fields=["totals", "updated_at"])
    return totals


def _booking_days(booking: Booking, totals: dict[str, object]) -> int:
    raw_days = totals.get("days")
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        days = booking.days
    if not days or days <= 0:
        days = booking.days or 1
    return max(days, 1)


def _pricing_breakdown(booking: Booking) -> dict[str, Decimal | int | dict[str, str]]:
    totals = _ensure_booking_totals(booking)
    rental_subtotal = _decimal_from_value(totals.get("rental_subtotal"))
    renter_fee_val = totals.get("renter_fee", totals.get("service_fee", "0"))
    renter_fee = _decimal_from_value(renter_fee_val)
    owner_payout = _decimal_from_value(totals.get("owner_payout"))
    owner_fee = _decimal_from_value(totals.get("owner_fee"))
    platform_total_default = renter_fee + owner_fee
    platform_fee_total = _decimal_from_value(
        totals.get("platform_fee_total"),
        platform_total_default,
    )
    damage_deposit = _decimal_from_value(totals.get("damage_deposit"))
    days = _booking_days(booking, totals)
    days_decimal = Decimal(days)
    if days_decimal > 0:
        rent_per_day = _quantize_money(rental_subtotal / days_decimal)
        renter_fee_per_day = _quantize_money(renter_fee / days_decimal)
        owner_payout_per_day = _quantize_money(owner_payout / days_decimal)
        platform_fee_per_day = (
            _quantize_money(platform_fee_total / days_decimal)
            if platform_fee_total > Decimal("0")
            else Decimal("0.00")
        )
    else:
        rent_per_day = renter_fee_per_day = owner_payout_per_day = platform_fee_per_day = Decimal(
            "0.00"
        )

    return {
        "totals": totals,
        "rental_subtotal": rental_subtotal,
        "renter_fee": renter_fee,
        "owner_payout": owner_payout,
        "platform_fee_total": platform_fee_total,
        "damage_deposit": damage_deposit,
        "rent_per_day": rent_per_day,
        "renter_fee_per_day": renter_fee_per_day,
        "owner_payout_per_day": owner_payout_per_day,
        "platform_fee_per_day": platform_fee_per_day,
        "days": days,
    }


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
        booking = serializer.save()
        create_system_message(
            booking,
            ChatMessage.SYSTEM_REQUEST_SENT,
            "Booking request sent",
        )

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
        unpaid_confirmed = Booking.objects.filter(
            owner=user,
            status=Booking.Status.CONFIRMED,
        ).only("id", "charge_payment_intent_id")
        unpaid_total = sum(1 for booking in unpaid_confirmed if is_pre_payment(booking))
        renter_unpaid_total = Booking.objects.filter(
            renter=user,
            status=Booking.Status.CONFIRMED,
        ).count()
        return Response(
            {
                "pending_requests": pending_total,
                "unpaid_bookings": unpaid_total,
                "renter_unpaid_bookings": renter_unpaid_total,
            },
            status=status.HTTP_200_OK,
        )

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
        create_system_message(
            booking,
            ChatMessage.SYSTEM_REQUEST_APPROVED,
            "Booking request approved",
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

        actor_override = (request.data.get("actor") or "").strip()
        if actor == "owner" and actor_override == "no_show":
            actor = "no_show"

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
        canceled = False
        if is_pre_payment(booking):
            mark_canceled(booking, actor=actor, auto=False, reason=cancel_reason)
            booking.save(update_fields=update_fields)
            canceled = True
        else:
            try:
                settlement = compute_refund_amounts(
                    booking=booking,
                    actor=actor,
                    today=timezone.localdate(),
                )
                apply_cancellation_settlement(booking, settlement)
            except StripeTransientError:
                return Response(
                    {"detail": "Temporary payment issue while refunding; please retry."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            except StripePaymentError as exc:
                message = str(exc) or "Unable to process refund for this cancellation."
                return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
            except StripeConfigurationError:
                logger.exception(
                    "Stripe configuration error while canceling booking %s", booking.id
                )
                return Response(
                    {"detail": "Payment processor is not configured; please try again later."},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            mark_canceled(booking, actor=actor, auto=False, reason=cancel_reason)
            booking.save(update_fields=update_fields)
            canceled = True

        if actor in {"owner", "no_show"}:
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
        if canceled:
            create_system_message(
                booking,
                ChatMessage.SYSTEM_BOOKING_CANCELLED,
                "Booking cancelled",
                close_chat=True,
            )
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="mark-late")
    def mark_late(self, request, *args, **kwargs):
        """Charge a renter for a late return (owner-only)."""
        booking: Booking = self.get_object()
        if booking.owner_id != request.user.id:
            return Response(
                {"detail": "Only the listing owner can mark this booking as late."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status != Booking.Status.PAID:
            return Response(
                {"detail": "Only paid bookings can be marked late."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        extra_days = extra_days_for_late(today, booking)
        if extra_days <= 0:
            return Response(
                {"detail": "Booking is not overdue."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pricing = _pricing_breakdown(booking)
        multiplier = Decimal(extra_days)
        extra_rent = _quantize_money(pricing["rent_per_day"] * multiplier)
        extra_service_fee = _quantize_money(pricing["renter_fee_per_day"] * multiplier)
        extra_charge_total = _quantize_money(extra_rent + extra_service_fee)
        if extra_charge_total <= Decimal("0"):
            return Response(
                {"detail": "Calculated late fee must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            create_late_fee_payment_intent(
                booking=booking,
                amount=extra_charge_total,
                description="Late return fee",
            )
        except StripeTransientError:
            return Response(
                {"detail": "Temporary payment issue while charging late fee; please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripeConfigurationError:
            logger.exception(
                "Stripe configuration error while charging late fee for %s", booking.id
            )
            return Response(
                {"detail": "Payment processor not configured; please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripePaymentError as exc:
            message = str(exc) or "Unable to process late fee."
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        owner_extra = _quantize_money(pricing["owner_payout_per_day"] * multiplier)
        if owner_extra > Decimal("0"):
            log_transaction(
                user=booking.owner,
                booking=booking,
                kind=Transaction.Kind.OWNER_EARNING,
                amount=owner_extra,
            )

        platform_extra = _quantize_money(pricing["platform_fee_per_day"] * multiplier)
        if platform_extra > Decimal("0"):
            platform_user = get_platform_ledger_user()
            if platform_user:
                log_transaction(
                    user=platform_user,
                    booking=booking,
                    kind=Transaction.Kind.PLATFORM_FEE,
                    amount=platform_extra,
                )
            else:
                logger.info(
                    "Platform fee %s for late fee booking %s not logged; platform account missing.",
                    platform_extra,
                    booking.id,
                )

        logger.info("chat: Booking %s marked late (%s extra days)", booking.id, extra_days)
        data = self.get_serializer(booking).data
        data["late_fee_days"] = extra_days
        data["late_fee_amount"] = format(extra_charge_total, ".2f")
        return Response(data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="mark-not-returned")
    def mark_not_returned(self, request, *args, **kwargs):
        """Capture damage deposit when an item is not returned (owner-only)."""
        booking: Booking = self.get_object()
        if booking.owner_id != request.user.id:
            return Response(
                {"detail": "Only the listing owner can mark this booking as not returned."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status != Booking.Status.PAID or not booking.pickup_confirmed_at:
            return Response(
                {"detail": "Booking must be in progress (paid and picked up) to capture deposit."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deposit_intent_id = (booking.deposit_hold_id or "").strip()
        if not deposit_intent_id:
            return Response(
                {"detail": "This booking has no damage deposit hold to capture."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = timezone.localdate()
        if not is_severely_overdue(today, booking, threshold_days=2):
            return Response(
                {"detail": "Booking must be overdue by at least 2 days to capture the deposit."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pricing = _pricing_breakdown(booking)
        damage_deposit = pricing["damage_deposit"]
        if damage_deposit <= Decimal("0"):
            return Response(
                {"detail": "No damage deposit amount is available for capture."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requested_amount_raw = (request.data.get("amount") or "").strip()
        capture_amount = damage_deposit
        if requested_amount_raw:
            try:
                parsed = Decimal(str(requested_amount_raw))
            except (InvalidOperation, ValueError):
                return Response(
                    {"detail": "amount must be a valid decimal string."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            capture_amount = _quantize_money(parsed)
        capture_amount = min(capture_amount, damage_deposit)
        if capture_amount <= Decimal("0"):
            return Response(
                {"detail": "Capture amount must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            capture_deposit_amount(
                booking=booking,
                amount=capture_amount,
            )
        except StripeTransientError:
            return Response(
                {"detail": "Temporary payment issue while capturing deposit; please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripeConfigurationError:
            logger.exception(
                "Stripe configuration error while capturing deposit for booking %s", booking.id
            )
            return Response(
                {"detail": "Payment processor not configured; please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripePaymentError as exc:
            message = str(exc) or "Unable to capture deposit hold."
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        logger.info(
            "chat: Booking %s marked as not returned, deposit captured (%s).",
            booking.id,
            capture_amount,
        )
        data = self.get_serializer(booking).data
        data["deposit_captured"] = format(capture_amount, ".2f")
        return Response(data, status=status.HTTP_200_OK)

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

        now = timezone.now()
        filing_window_hours = get_int("DISPUTE_FILING_WINDOW_HOURS", 24)
        update_fields = ["status", "updated_at"]
        booking.status = Booking.Status.COMPLETED
        if booking.return_confirmed_at and booking.dispute_window_expires_at is None:
            booking.dispute_window_expires_at = booking.return_confirmed_at + timedelta(
                hours=filing_window_hours
            )
            update_fields.insert(1, "dispute_window_expires_at")
        elif booking.dispute_window_expires_at is None:
            booking.dispute_window_expires_at = now + timedelta(hours=filing_window_hours)
            update_fields.insert(1, "dispute_window_expires_at")

        booking.save(update_fields=update_fields)
        create_system_message(
            booking,
            ChatMessage.SYSTEM_BOOKING_COMPLETED,
            "Booking completed",
            close_chat=True,
        )
        if booking.renter_id:
            try:
                notification_tasks.send_booking_completed_email.delay(booking.renter_id, booking.id)
            except Exception:
                logger.info(
                    "notifications: could not queue send_booking_completed_email for booking %s",
                    booking.id,
                    exc_info=True,
                )
        return Response(self.get_serializer(booking).data)

    @action(detail=True, methods=["post"], url_path="renter-return")
    def renter_return(self, request, *args, **kwargs):
        """Allow renters to mark a booking as returned after the end date."""
        booking: Booking = self.get_object()
        if booking.renter_id != request.user.id:
            return Response(
                {"detail": "Only the renter can mark the tool as returned."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status != Booking.Status.PAID or not booking.pickup_confirmed_at:
            return Response(
                {
                    "detail": (
                        "Booking must be in progress and past its end date before marking return."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if booking.end_date and timezone.localdate() < booking.end_date:
            return Response(
                {"detail": "Booking must be past its end date before marking return."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        booking.returned_by_renter_at = timezone.now()
        booking.save(update_fields=["returned_by_renter_at", "updated_at"])

        payload = {"booking_id": booking.id, "triggered_by": request.user.id}
        push_event(booking.owner_id, "booking:return_requested", payload)
        push_event(booking.renter_id, "booking:return_requested", payload)

        return Response(self.get_serializer(booking).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="owner-mark-returned")
    def owner_mark_returned(self, request, *args, **kwargs):
        """Allow owners to confirm a renter-marked return."""
        booking: Booking = self.get_object()
        if booking.owner_id != request.user.id:
            return Response(
                {"detail": "Only the listing owner can confirm the return."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.status != Booking.Status.PAID:
            return Response(
                {"detail": "Booking must be in a paid state to confirm return."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not booking.returned_by_renter_at:
            return Response(
                {"detail": "Renter must mark return before owner confirmation."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        booking.return_confirmed_at = now
        filing_window_hours = get_int("DISPUTE_FILING_WINDOW_HOURS", 24)
        booking.dispute_window_expires_at = now + timedelta(hours=filing_window_hours)
        booking.save(
            update_fields=["return_confirmed_at", "dispute_window_expires_at", "updated_at"]
        )
        return Response(self.get_serializer(booking).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="before-photos/presign")
    def before_photos_presign(self, request, *args, **kwargs):
        """Return a presigned PUT URL so renters can upload before photos."""
        booking: Booking = self.get_object()
        if booking.renter_id != request.user.id:
            return Response(
                {"detail": "Only the renter can upload before photos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.is_terminal():
            return Response(
                {"detail": "Cannot upload photos for a canceled or completed booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        content_md5 = request.data.get("content_md5")
        size_raw = request.data.get("size")
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_hint = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_hint <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        max_bytes = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
        if max_bytes and size_hint > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        key = booking_object_key(
            booking_id=booking.id,
            user_id=request.user.id,
            filename=filename,
        )
        try:
            presigned = presign_put(
                key,
                content_type=content_type,
                content_md5=content_md5,
                size_hint=size_hint,
            )
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "key": key,
                "upload_url": presigned["upload_url"],
                "headers": presigned["headers"],
                "max_bytes": getattr(settings, "S3_MAX_UPLOAD_BYTES", None),
                "tagging": "av-status=pending",
            }
        )

    @action(detail=True, methods=["post"], url_path="before-photos/complete")
    def before_photos_complete(self, request, *args, **kwargs):
        """Persist a booking photo record and queue antivirus processing."""
        booking: Booking = self.get_object()
        if booking.renter_id != request.user.id:
            return Response(
                {"detail": "Only the renter can upload before photos."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if booking.is_terminal():
            return Response(
                {"detail": "Cannot upload photos for a canceled or completed booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        key = request.data.get("key")
        etag = request.data.get("etag")
        if not key or not etag:
            return Response(
                {"detail": "key and etag required."}, status=status.HTTP_400_BAD_REQUEST
            )

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        size_raw = request.data.get("size")
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_int = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_int <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        max_bytes = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
        if max_bytes and size_int > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        photo_url = public_url(key)
        photo, _ = BookingPhoto.objects.get_or_create(
            booking=booking,
            uploaded_by=request.user,
            s3_key=key,
            defaults={"role": BookingPhoto.Role.BEFORE},
        )
        photo.role = BookingPhoto.Role.BEFORE
        photo.url = photo_url
        photo.filename = filename
        photo.content_type = content_type
        photo.size = size_int
        photo.etag = (etag or "").strip('"')
        photo.status = BookingPhoto.Status.PENDING
        photo.av_status = BookingPhoto.AVStatus.PENDING
        photo.width = None
        photo.height = None
        photo.save()

        meta = {
            "etag": etag,
            "filename": filename,
            "content_type": content_type,
            "size": size_int,
            "role": BookingPhoto.Role.BEFORE,
        }
        scan_and_finalize_booking_photo.delay(
            key=key,
            booking_id=booking.id,
            uploaded_by_id=request.user.id,
            meta=meta,
        )

        if not booking.before_photos_uploaded_at:
            booking.before_photos_uploaded_at = timezone.now()
            booking.save(update_fields=["before_photos_uploaded_at", "updated_at"])

        return Response({"status": "queued", "key": key}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="after-photos/presign")
    def after_photos_presign(self, request, *args, **kwargs):
        """Return a presigned PUT URL so participants can upload after photos."""
        booking: Booking = self.get_object()
        if booking.is_terminal():
            return Response(
                {"detail": "Cannot upload photos for a canceled or completed booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        content_md5 = request.data.get("content_md5")
        size_raw = request.data.get("size")
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_hint = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_hint <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        max_bytes = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
        if max_bytes and size_hint > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        key = booking_object_key(
            booking_id=booking.id,
            user_id=request.user.id,
            filename=filename,
        )
        try:
            presigned = presign_put(
                key,
                content_type=content_type,
                content_md5=content_md5,
                size_hint=size_hint,
            )
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "key": key,
                "upload_url": presigned["upload_url"],
                "headers": presigned["headers"],
                "max_bytes": getattr(settings, "S3_MAX_UPLOAD_BYTES", None),
                "tagging": "av-status=pending",
            }
        )

    @action(detail=True, methods=["post"], url_path="after-photos/complete")
    def after_photos_complete(self, request, *args, **kwargs):
        """Persist an after photo record and queue antivirus processing."""
        booking: Booking = self.get_object()
        if booking.is_terminal():
            return Response(
                {"detail": "Cannot upload photos for a canceled or completed booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        key = request.data.get("key")
        etag = request.data.get("etag")
        if not key or not etag:
            return Response(
                {"detail": "key and etag required."}, status=status.HTTP_400_BAD_REQUEST
            )

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        size_raw = request.data.get("size")
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_int = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_int <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        max_bytes = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
        if max_bytes and size_int > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        photo_url = public_url(key)
        photo, _ = BookingPhoto.objects.get_or_create(
            booking=booking,
            uploaded_by=request.user,
            s3_key=key,
            defaults={"role": BookingPhoto.Role.AFTER},
        )
        photo.role = BookingPhoto.Role.AFTER
        photo.url = photo_url
        photo.filename = filename
        photo.content_type = content_type
        photo.size = size_int
        photo.etag = (etag or "").strip('"')
        photo.status = BookingPhoto.Status.PENDING
        photo.av_status = BookingPhoto.AVStatus.PENDING
        photo.width = None
        photo.height = None
        photo.save()

        meta = {
            "etag": etag,
            "filename": filename,
            "content_type": content_type,
            "size": size_int,
            "role": BookingPhoto.Role.AFTER,
        }
        scan_and_finalize_booking_photo.delay(
            key=key,
            booking_id=booking.id,
            uploaded_by_id=request.user.id,
            meta=meta,
        )

        return Response({"status": "queued", "key": key}, status=status.HTTP_202_ACCEPTED)

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
        logger.info("chat: Booking %s picked up", booking.id)
        create_system_message(
            booking,
            ChatMessage.SYSTEM_TOOL_PICKED_UP,
            "Tool picked up",
        )
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
            charge_id = create_booking_charge_intent(
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
        booking.renter_stripe_customer_id = customer_id or ""
        booking.renter_stripe_payment_method_id = payment_method_id or ""
        booking.status = Booking.Status.PAID
        booking.save(
            update_fields=[
                "status",
                "charge_payment_intent_id",
                "renter_stripe_customer_id",
                "renter_stripe_payment_method_id",
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
        create_system_message(
            booking,
            ChatMessage.SYSTEM_PAYMENT_MADE,
            "Payment received",
        )
        return Response(self.get_serializer(booking).data, status=status.HTTP_200_OK)
