"""Domain helpers for booking validation and state transitions."""

from __future__ import annotations

from datetime import date
from typing import Optional

from django.core.exceptions import ValidationError

from listings.models import Listing

from .models import Booking


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
    active_statuses = [Booking.Status.REQUESTED, Booking.Status.CONFIRMED]
    qs = Booking.objects.filter(listing=listing, status__in=active_statuses)
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


def assert_can_cancel(booking: Booking) -> None:
    """Ensure the booking can be canceled."""
    if booking.status not in {Booking.Status.REQUESTED, Booking.Status.CONFIRMED}:
        raise ValidationError({"status": ["Only requested or confirmed bookings can be canceled."]})


def assert_can_complete(booking: Booking) -> None:
    """Ensure the booking can be marked as complete."""
    if booking.status != Booking.Status.CONFIRMED:
        raise ValidationError({"status": ["Only confirmed bookings can be completed."]})
