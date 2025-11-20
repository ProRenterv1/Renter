"""Tests for bookings Celery tasks."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking
from bookings.tasks import auto_expire_stale_bookings

pytestmark = pytest.mark.django_db


def test_auto_expire_stale_bookings(monkeypatch, booking_factory):
    today = timezone.localdate()
    requested = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    confirmed_pre_payment = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=3),
        status=Booking.Status.CONFIRMED,
    )
    confirmed_paid = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=4),
        status=Booking.Status.CONFIRMED,
    )
    confirmed_paid.charge_payment_intent_id = "pi_paid"
    confirmed_paid.save(update_fields=["charge_payment_intent_id"])

    future_booking = booking_factory(
        start_date=today + timedelta(days=5),
        end_date=today + timedelta(days=7),
        status=Booking.Status.REQUESTED,
    )

    notified = []

    def fake_delay(booking_id: int):
        notified.append(booking_id)

    monkeypatch.setattr(
        "bookings.tasks.notification_tasks.send_booking_expired_email.delay",
        fake_delay,
    )

    expired_count = auto_expire_stale_bookings()

    assert expired_count == 2
    requested.refresh_from_db()
    confirmed_pre_payment.refresh_from_db()
    confirmed_paid.refresh_from_db()
    future_booking.refresh_from_db()

    assert requested.status == Booking.Status.CANCELED
    assert requested.canceled_by == Booking.CanceledBy.SYSTEM
    assert requested.auto_canceled is True

    assert confirmed_pre_payment.status == Booking.Status.CANCELED
    assert confirmed_pre_payment.canceled_by == Booking.CanceledBy.SYSTEM
    assert confirmed_pre_payment.auto_canceled is True

    assert confirmed_paid.status == Booking.Status.CONFIRMED
    assert future_booking.status == Booking.Status.REQUESTED
    assert set(notified) == {requested.id, confirmed_pre_payment.id}
