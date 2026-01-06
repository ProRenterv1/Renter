"""Tests for automatically releasing deposit holds."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from backend.payments import stripe_api
from bookings.models import Booking
from bookings.tasks import auto_release_deposits
from payments.models import Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configure_stripe(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_123"


@pytest.fixture
def stripe_intent_stub(monkeypatch):
    state: dict[str, object] = {"status": "requires_capture", "cancel_calls": []}

    def fake_retrieve(intent_id: str):
        return SimpleNamespace(id=intent_id, status=state["status"])

    def fake_cancel(intent_id: str):
        state["cancel_calls"].append(intent_id)
        return SimpleNamespace(id=intent_id, status="canceled")

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", fake_retrieve)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "cancel", fake_cancel)
    return state


def test_auto_release_deposits_releases_when_due(booking_factory, stripe_intent_stub):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.COMPLETED,
        deposit_hold_id="pi_test_deposit",
        deposit_release_scheduled_at=timezone.now() - timedelta(hours=2),
        totals={"damage_deposit": "75.00"},
    )

    released = auto_release_deposits()

    assert released == 1
    booking.refresh_from_db()
    assert booking.deposit_released_at is not None
    tx = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        stripe_id="pi_test_deposit",
    ).first()
    assert tx is not None
    assert Decimal(tx.amount) == Decimal("75.00")
    assert stripe_intent_stub["cancel_calls"] == ["pi_test_deposit"]


def test_auto_release_deposits_skips_open_dispute(booking_factory, stripe_intent_stub):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.COMPLETED,
        deposit_hold_id="pi_test_dispute",
        deposit_release_scheduled_at=timezone.now() - timedelta(hours=1),
        dispute_window_expires_at=timezone.now() + timedelta(hours=3),
        totals={"damage_deposit": "50.00"},
    )

    released = auto_release_deposits()

    assert released == 0
    booking.refresh_from_db()
    assert booking.deposit_released_at is None
    assert (
        Transaction.objects.filter(
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        ).count()
        == 0
    )
    assert stripe_intent_stub["cancel_calls"] == []


def test_auto_release_deposits_handles_captured_intent(booking_factory, stripe_intent_stub):
    stripe_intent_stub["status"] = "succeeded"
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.COMPLETED,
        deposit_hold_id="pi_captured",
        deposit_release_scheduled_at=timezone.now() - timedelta(hours=1),
        totals={"damage_deposit": "100.00"},
    )

    released = auto_release_deposits()

    assert released == 1
    booking.refresh_from_db()
    assert booking.deposit_released_at is not None
    assert (
        Transaction.objects.filter(
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        ).count()
        == 0
    )
    assert stripe_intent_stub["cancel_calls"] == []
