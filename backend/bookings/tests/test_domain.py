"""Tests for booking domain validation helpers."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from bookings.domain import (
    assert_can_cancel,
    assert_can_complete,
    assert_can_confirm,
    assert_can_confirm_pickup,
    days_until_start,
    ensure_no_conflict,
    is_overdue,
    is_pre_payment,
    mark_canceled,
)
from bookings.models import Booking

pytestmark = pytest.mark.django_db


def future(days: int) -> date:
    return date.today() + timedelta(days=days)


def test_cannot_overlap_confirmed_booking(listing, booking_factory):
    start = future(5)
    end = start + timedelta(days=3)
    booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)

    with pytest.raises(ValidationError):
        ensure_no_conflict(listing, start, end)


def test_can_create_non_overlapping_booking(listing, booking_factory):
    start = future(7)
    end = start + timedelta(days=4)
    booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)

    before_start = start - timedelta(days=4)
    before_end = start
    after_start = end
    after_end = end + timedelta(days=3)

    # Adjacent ranges touching edges should be allowed.
    ensure_no_conflict(listing, before_start, before_end)
    ensure_no_conflict(listing, after_start, after_end)


def test_exclude_booking_id_allows_self_update(listing, booking_factory):
    start = future(9)
    end = start + timedelta(days=2)
    booking = booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)

    ensure_no_conflict(
        listing,
        start,
        end,
        exclude_booking_id=booking.id,
    )


def test_assert_can_confirm_allows_only_requested(booking_factory):
    booking = booking_factory(start_date=future(1), end_date=future(3))
    assert_can_confirm(booking)

    booking.status = Booking.Status.CONFIRMED
    with pytest.raises(ValidationError):
        assert_can_confirm(booking)


def test_assert_can_cancel_allows_requested_and_confirmed(booking_factory):
    booking = booking_factory(start_date=future(2), end_date=future(4))
    booking.status = Booking.Status.REQUESTED
    assert_can_cancel(booking)

    booking.status = Booking.Status.CONFIRMED
    assert_can_cancel(booking)

    booking.status = Booking.Status.CANCELED
    with pytest.raises(ValidationError):
        assert_can_cancel(booking)


def test_assert_can_complete_allows_only_confirmed(booking_factory):
    booking = booking_factory(
        start_date=future(3), end_date=future(5), status=Booking.Status.CONFIRMED
    )
    assert_can_complete(booking)

    booking.status = Booking.Status.REQUESTED
    with pytest.raises(ValidationError):
        assert_can_complete(booking)


def test_days_until_start_handles_missing_start(booking_factory):
    booking = booking_factory(start_date=future(5), end_date=future(7))
    today = date.today()
    assert days_until_start(today, booking) == (booking.start_date - today).days

    booking.start_date = None
    assert days_until_start(today, booking) == 0


def test_is_overdue_flags_dates_past_end(booking_factory):
    booking = booking_factory(start_date=future(1), end_date=future(3))
    assert not is_overdue(date.today(), booking)

    after_end = booking.end_date + timedelta(days=1)
    assert is_overdue(after_end, booking)

    booking.end_date = None
    assert not is_overdue(after_end, booking)


def test_assert_can_cancel_validates_actor_and_status(booking_factory):
    booking = booking_factory(start_date=future(2), end_date=future(4))

    assert_can_cancel(booking, actor="renter")
    booking.status = Booking.Status.PAID
    assert_can_cancel(booking, actor="owner")

    with pytest.raises(ValidationError):
        assert_can_cancel(booking, actor="invalid")  # type: ignore[arg-type]

    booking.status = Booking.Status.CANCELED
    with pytest.raises(ValidationError):
        assert_can_cancel(booking, actor="renter")


def test_assert_can_confirm_pickup_happy_path(booking_factory):
    booking = booking_factory(
        start_date=future(3),
        end_date=future(6),
        status=Booking.Status.PAID,
        before_photos_uploaded_at=timezone.now(),
    )
    assert_can_confirm_pickup(booking)


def test_assert_can_confirm_pickup_requires_paid_and_photos(booking_factory):
    booking = booking_factory(start_date=future(1), end_date=future(2))
    with pytest.raises(ValidationError):
        assert_can_confirm_pickup(booking)

    booking.status = Booking.Status.PAID
    booking.before_photos_uploaded_at = None
    with pytest.raises(ValidationError):
        assert_can_confirm_pickup(booking)


def test_is_pre_payment_checks_charge_intent(booking_factory):
    booking = booking_factory(start_date=future(5), end_date=future(7))
    booking.charge_payment_intent_id = ""
    assert is_pre_payment(booking)

    booking.charge_payment_intent_id = "pi_123"
    assert not is_pre_payment(booking)


def test_mark_canceled_updates_fields(booking_factory):
    booking = booking_factory(
        start_date=future(3), end_date=future(6), status=Booking.Status.CONFIRMED
    )
    mark_canceled(booking, actor="system", auto=True, reason="Expired before payment")

    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.SYSTEM
    assert booking.canceled_reason == "Expired before payment"
    assert booking.auto_canceled is True
