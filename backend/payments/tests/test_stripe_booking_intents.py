from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from backend.payments import stripe_api as stripe_api
from bookings.models import Booking
from listings.models import Listing
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
        totals={
            "rental_subtotal": "80.00",
            "service_fee": "20.00",
            "owner_fee": "4.00",
            "platform_fee_total": "24.00",
            "owner_payout": "76.00",
            "damage_deposit": "15.00",
            "total_charge": "115.00",
        },
    )


def test_to_cents_rounding():
    assert stripe_api._to_cents(Decimal("10.005")) == 1001
    assert stripe_api._to_cents(Decimal("0.004")) == 0


def test_create_booking_payment_intents_logs_transactions(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"

    owner = User.objects.create_user(username="owner-ledger", password="x")
    renter = User.objects.create_user(username="renter-ledger", password="x")
    listing = create_listing(owner)
    booking = create_booking(listing, owner, renter)

    intent_store: dict[str, DummyIntent] = {}
    create_calls = {"count": 0}
    created_calls: list[dict] = []

    def fake_retrieve(intent_id: str, *, label: str):
        if not intent_id:
            return None
        return intent_store.get(intent_id)

    def fake_create(**kwargs):
        created_calls.append(kwargs)
        key_parts = kwargs["idempotency_key"].split(":")
        if kwargs["metadata"]["kind"] == "booking_charge":
            assert key_parts[-4] == "charge_dest_v1"
            assert key_parts[-3].isdigit()
            assert key_parts[-2].isdigit()
            assert key_parts[-1] == "acct_test_owner"
        else:
            assert key_parts[-2] == "deposit"
            assert key_parts[-1].isdigit()
        create_calls["count"] += 1
        kind = kwargs["metadata"]["kind"]
        intent_id = f"pi_{kind}_{create_calls['count']}"
        intent = DummyIntent(intent_id)
        intent_store[intent_id] = intent
        return intent

    monkeypatch.setattr(stripe_api, "_retrieve_payment_intent", fake_retrieve)
    payment_intent_mock = type("MockPI", (), {"create": staticmethod(fake_create)})
    monkeypatch.setattr(stripe_api.stripe, "PaymentIntent", payment_intent_mock)
    monkeypatch.setattr(stripe_api, "_ensure_payment_method_for_customer", lambda *a, **k: None)
    monkeypatch.setattr(
        stripe_api,
        "ensure_connect_account",
        lambda *_args, **_kwargs: SimpleNamespace(
            stripe_account_id="acct_test_owner",
            payouts_enabled=True,
            charges_enabled=True,
            is_fully_onboarded=True,
        ),
    )

    charge_id = stripe_api.create_booking_charge_intent(
        booking=booking,
        customer_id="cus_mock",
        payment_method_id="pm_mock",
    )

    charge_txn = Transaction.objects.get(kind=Transaction.Kind.BOOKING_CHARGE)
    assert Transaction.objects.count() == 1
    assert charge_txn.amount == Decimal("100.00")
    assert charge_txn.stripe_id == charge_id

    assert booking.charge_payment_intent_id == charge_id
    assert booking.deposit_hold_id == ""
    assert create_calls["count"] == 1

    deposit_id = stripe_api.create_booking_deposit_hold_intent(
        booking=booking,
        customer_id="cus_mock",
        payment_method_id="pm_mock",
    )

    deposit_txn = Transaction.objects.get(kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE)
    assert Transaction.objects.count() == 2
    assert deposit_txn.amount == Decimal("15.00")
    assert deposit_txn.stripe_id == deposit_id

    assert booking.deposit_hold_id == deposit_id
    assert create_calls["count"] == 2

    booking.refresh_from_db()
    assert booking.charge_payment_intent_id == charge_id
    assert booking.deposit_hold_id == deposit_id

    # Second invocation should reuse intents and not create duplicate ledger entries.
    stripe_api.create_booking_deposit_hold_intent(
        booking=booking,
        customer_id="cus_mock",
        payment_method_id="pm_mock",
    )

    assert Transaction.objects.count() == 2
    assert Transaction.objects.filter(kind=Transaction.Kind.BOOKING_CHARGE).count() == 1
    assert Transaction.objects.filter(kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE).count() == 1
    assert create_calls["count"] == 2

    charge_call, deposit_call = created_calls
    assert charge_call["capture_method"] == "automatic"
    assert deposit_call["capture_method"] == "manual"
    assert charge_call["automatic_payment_methods"]["enabled"] is True
    assert charge_call["automatic_payment_methods"]["allow_redirects"] == "never"
    assert deposit_call["automatic_payment_methods"]["enabled"] is True
    assert deposit_call["automatic_payment_methods"]["allow_redirects"] == "never"
    assert charge_call["application_fee_amount"] == 2400
    assert charge_call["transfer_data"]["destination"] == "acct_test_owner"
    assert charge_call["transfer_data"]["amount"] == 7600
    assert charge_call["transfer_group"] == f"booking:{booking.id}"
    assert charge_call["on_behalf_of"] == "acct_test_owner"


def test_create_booking_charge_requires_onboarded_owner(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"
    settings.STRIPE_BOOKINGS_DESTINATION_CHARGES = True

    owner = User.objects.create_user(username="owner-onboard", password="x")
    renter = User.objects.create_user(username="renter-onboard", password="x")
    listing = create_listing(owner)
    booking = create_booking(listing, owner, renter)

    monkeypatch.setattr(stripe_api, "_ensure_payment_method_for_customer", lambda *a, **k: None)
    monkeypatch.setattr(
        stripe_api,
        "ensure_connect_account",
        lambda *_args, **_kwargs: SimpleNamespace(
            stripe_account_id="acct_test_owner",
            payouts_enabled=False,
            charges_enabled=False,
            is_fully_onboarded=False,
        ),
    )

    with pytest.raises(stripe_api.StripePaymentError):
        stripe_api.create_booking_charge_intent(
            booking=booking,
            customer_id="cus_mock",
            payment_method_id="pm_mock",
        )
