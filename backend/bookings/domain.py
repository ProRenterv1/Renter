"""Domain helpers for booking validation and state transitions."""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from django.core.exceptions import ValidationError

from listings.models import Listing

from .models import Booking, BookingPhoto

ACTIVE_BOOKING_STATUSES = (
    Booking.Status.REQUESTED,
    Booking.Status.CONFIRMED,
    Booking.Status.PAID,
)

CancelActor = Literal["renter", "owner", "system", "no_show"]


def days_until_start(today: date, booking: Booking) -> int:
    """Return (booking.start_date - today).days."""
    if not booking.start_date:
        return 0
    return (booking.start_date - today).days


def is_overdue(today: date, booking: Booking) -> bool:
    """
    Return True if booking is overdue:
    today strictly greater than end_date (end-exclusive).
    """
    if not booking.end_date:
        return False
    return today > booking.end_date


def validate_booking_dates(start_date: date | None, end_date: date | None) -> None:
    """Validate that the provided dates exist and form a valid range."""
    if not start_date or not end_date:
        raise ValidationError({"non_field_errors": ["Start and end dates are required."]})
    if start_date >= end_date:
        raise ValidationError({"end_date": ["End date must be after start date."]})


def ensure_no_conflict(
    listing: Listing,
    start_date: date,
    end_date: date,
    *,
    exclude_booking_id: Optional[int] = None,
) -> None:
    """Ensure there are no overlapping bookings for the listing."""
    qs = Booking.objects.filter(listing=listing, status__in=ACTIVE_BOOKING_STATUSES)
    if exclude_booking_id is not None:
        qs = qs.exclude(pk=exclude_booking_id)
    conflicts = qs.filter(start_date__lt=end_date, end_date__gt=start_date)
    if conflicts.exists():
        raise ValidationError(
            {"non_field_errors": ["Requested dates are not available for this listing."]}
        )


def assert_can_confirm(booking: Booking) -> None:
    """Ensure the booking can be confirmed."""
    if booking.status != Booking.Status.REQUESTED:
        raise ValidationError({"status": ["Only requested bookings can be confirmed."]})


def assert_can_cancel(booking: Booking, actor: CancelActor | None = None) -> None:
    """
    Ensure the booking can be canceled given the actor.
    - Only requested/confirmed/paid may be canceled.
    - Completed/canceled cannot be canceled again.
    - Actor-specific rules can be tightened later.
    """
    if booking.status not in {
        Booking.Status.REQUESTED,
        Booking.Status.CONFIRMED,
        Booking.Status.PAID,
    }:
        raise ValidationError(
            {"status": ["Only requested, confirmed, or paid bookings can be canceled."]}
        )
    if actor is not None and actor not in {"renter", "owner", "system", "no_show"}:
        raise ValidationError({"non_field_errors": ["Invalid cancel actor."]})


def assert_can_complete(booking: Booking) -> None:
    """Ensure the booking can be marked as complete."""
    if booking.status not in {Booking.Status.CONFIRMED, Booking.Status.PAID}:
        raise ValidationError({"status": ["Only confirmed or paid bookings can be completed."]})


def assert_can_confirm_pickup(booking: Booking) -> None:
    """
    Ensure the booking is in a state where owner can confirm pickup.
    """
    if booking.status != Booking.Status.PAID:
        raise ValidationError({"status": ["Only paid bookings can be confirmed as picked up."]})
    if booking.is_terminal():
        raise ValidationError({"status": ["This booking is not active."]})
    if booking.before_photos_required and not booking.before_photos_uploaded_at:
        raise ValidationError(
            {"non_field_errors": ["Before photos must be uploaded before confirming pickup."]}
        )
    if booking.before_photos_required:
        has_clean_before = BookingPhoto.objects.filter(
            booking=booking,
            role=BookingPhoto.Role.BEFORE,
            status=BookingPhoto.Status.ACTIVE,
            av_status=BookingPhoto.AVStatus.CLEAN,
        ).exists()
        if not has_clean_before:
            raise ValidationError(
                {
                    "non_field_errors": [
                        "At least one clean 'before' photo is required before pickup confirmation."
                    ]
                }
            )


def is_pre_payment(booking: Booking) -> bool:
    """
    Return True if the booking has no associated charge intent yet.
    """
    return not (getattr(booking, "charge_payment_intent_id", "") or "").strip()


def extra_days_for_late(today: date, booking: Booking, *, max_days: int = 2) -> int:
    """
    Return clamped extra days to charge for a late return.

    When the booking is overdue, clamp the number of late days to [1, max_days].
    """
    if not booking.end_date or max_days <= 0:
        return 0
    if not is_overdue(today, booking):
        return 0
    days_late = max((today - booking.end_date).days, 0)
    if days_late <= 0:
        return 0
    return max(1, min(days_late, max_days))


def is_severely_overdue(today: date, booking: Booking, *, threshold_days: int = 2) -> bool:
    """Return True when the booking has been overdue for at least threshold_days."""
    if not booking.end_date:
        return False
    if threshold_days <= 0:
        threshold_days = 0
    days_late = (today - booking.end_date).days
    return days_late >= threshold_days


def mark_canceled(
    booking: Booking,
    *,
    actor: CancelActor,
    auto: bool,
    reason: str | None = None,
) -> None:
    """
    Mutate the provided booking instance into a canceled state.
    """
    booking.status = Booking.Status.CANCELED
    booking.canceled_by = actor
    if reason:
        booking.canceled_reason = reason
    booking.auto_canceled = auto
