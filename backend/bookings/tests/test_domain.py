"""Tests for booking domain validation helpers."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError

from bookings.domain import (
    assert_can_cancel,
    assert_can_complete,
    assert_can_confirm,
    ensure_no_conflict,
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
