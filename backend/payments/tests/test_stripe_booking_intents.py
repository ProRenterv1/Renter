from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model

from bookings.models import Booking
from listings.models import Listing
from payments import stripe_api
from payments.models import Transaction

pytestmark = pytest.mark.django_db

User = get_user_model()


class DummyIntent:
    def __init__(self, intent_id: str):
        self.id = intent_id


def create_listing(owner):
    return Listing.objects.create(
        owner=owner,
        title="Cordless Drill",
        description="Test listing",
        daily_price_cad=25,
        replacement_value_cad=200,
        damage_deposit_cad=50,
        city="Edmonton",
        postal_code="T5K 2M5",
        is_active=True,
        is_available=True,
    )


def create_booking(listing, owner, renter):
    start = date.today()
    return Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=start,
        end_date=start + timedelta(days=1),
        totals={"total_charge": "100.00", "damage_deposit": "20.00"},
    )


def test_create_booking_payment_intents_logs_transactions(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"

    owner = User.objects.create_user(username="owner-ledger", password="x")
    renter = User.objects.create_user(username="renter-ledger", password="x")
    listing = create_listing(owner)
    booking = create_booking(listing, owner, renter)

    intent_store: dict[str, DummyIntent] = {}
    create_calls = {"count": 0}

    def fake_retrieve(intent_id: str, *, label: str):
        if not intent_id:
            return None
        return intent_store.get(intent_id)

    def fake_create(**kwargs):
        key_suffix = kwargs["idempotency_key"].split(":")[-1]
        create_calls["count"] += 1
        intent_id = f"pi_{key_suffix}_{create_calls['count']}"
        intent = DummyIntent(intent_id)
        intent_store[intent_id] = intent
        return intent

    monkeypatch.setattr(stripe_api, "_retrieve_payment_intent", fake_retrieve)
    monkeypatch.setattr(
        stripe_api.stripe,
        "PaymentIntent",
        type("MockPI", (), {"create": staticmethod(fake_create)}),
    )

    charge_id, deposit_id = stripe_api.create_booking_payment_intents(
        booking=booking,
        customer_id="",
        payment_method_id="pm_mock",
    )

    charge_txn = Transaction.objects.get(kind=Transaction.Kind.BOOKING_CHARGE)
    deposit_txn = Transaction.objects.get(kind=Transaction.Kind.DAMAGE_DEPOSIT_HOLD)
    assert Transaction.objects.count() == 2
    assert charge_txn.direction == Transaction.Direction.DEBIT
    assert charge_txn.amount_cents == 8000
    assert deposit_txn.direction == Transaction.Direction.DEBIT
    assert deposit_txn.amount_cents == 2000

    assert create_calls["count"] == 2

    booking.charge_payment_intent_id = charge_id
    booking.deposit_hold_id = deposit_id
    booking.save(update_fields=["charge_payment_intent_id", "deposit_hold_id", "updated_at"])

    # Second invocation should reuse intents and not create duplicate ledger entries.
    stripe_api.create_booking_payment_intents(
        booking=booking,
        customer_id="",
        payment_method_id="pm_mock",
    )

    assert Transaction.objects.count() == 2
    assert Transaction.objects.filter(kind=Transaction.Kind.BOOKING_CHARGE).count() == 1
    assert Transaction.objects.filter(kind=Transaction.Kind.DAMAGE_DEPOSIT_HOLD).count() == 1
    assert create_calls["count"] == 2
