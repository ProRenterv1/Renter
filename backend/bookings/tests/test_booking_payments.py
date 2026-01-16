"""Tests covering Stripe payment behavior for booking creation."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from rest_framework.test import APIClient

from backend.payments import stripe_api as stripe_api
from bookings.models import Booking
from listings.models import Listing
from listings.services import compute_booking_totals

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configure_stripe(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_123"
    settings.STRIPE_ENV = "test"


@pytest.fixture(autouse=True)
def mock_stripe_payment_methods(monkeypatch):
    state: dict[str, str | None] = {}

    def fake_retrieve(payment_method_id):
        return SimpleNamespace(id=payment_method_id, customer=state.get(payment_method_id))

    def fake_attach(payment_method_id, *, customer):
        state[payment_method_id] = customer
        return SimpleNamespace(id=payment_method_id, customer=customer)

    def fake_detach(payment_method_id):
        state.pop(payment_method_id, None)
        return SimpleNamespace(id=payment_method_id, customer=None)

    monkeypatch.setattr(
        stripe.PaymentMethod,
        "retrieve",
        staticmethod(fake_retrieve),
    )
    monkeypatch.setattr(
        stripe.PaymentMethod,
        "attach",
        staticmethod(fake_attach),
    )
    monkeypatch.setattr(
        stripe.PaymentMethod,
        "detach",
        staticmethod(fake_detach),
    )


@pytest.fixture(autouse=True)
def mock_connect_account(monkeypatch):
    payout_account = SimpleNamespace(
        stripe_account_id="acct_test_owner",
        payouts_enabled=True,
        charges_enabled=True,
        is_fully_onboarded=True,
    )
    monkeypatch.setattr(stripe_api, "ensure_connect_account", lambda _user: payout_account)
    return payout_account


def auth(user):
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = token_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def booking_payload(listing, start, end, **extra):
    payload = {
        "listing": listing.id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }
    payload.update(extra)
    return payload


def test_booking_create_charges_and_defers_deposit_hold(renter_user, listing, monkeypatch):
    client = auth(renter_user)
    start = date.today() + timedelta(days=4)
    end = start + timedelta(days=3)

    created_calls = []

    def fake_create(**kwargs):
        created_calls.append(kwargs)
        kind = kwargs["metadata"]["kind"]
        if kind == "booking_charge":
            return SimpleNamespace(id="pi_charge_123")
        return SimpleNamespace(id="pi_deposit_456")

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "create", fake_create)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", lambda *args, **kwargs: None)

    resp = client.post(
        "/api/bookings/",
        booking_payload(
            listing,
            start,
            end,
            stripe_payment_method_id="pm_123",
            stripe_customer_id="cus_123",
        ),
        format="json",
    )

    assert resp.status_code == 201, resp.data

    booking = Booking.objects.get(pk=resp.data["id"])
    assert booking.charge_payment_intent_id == "pi_charge_123"
    assert booking.deposit_hold_id == ""
    assert booking.totals
    assert booking.renter_stripe_customer_id == "cus_123"
    assert booking.renter_stripe_payment_method_id == "pm_123"
    assert booking.paid_at is not None

    assert len(created_calls) == 1
    (charge_call,) = created_calls

    rental_subtotal = Decimal(booking.totals["rental_subtotal"])
    renter_fee_total = Decimal(
        booking.totals.get(
            "renter_fee_total",
            booking.totals.get("service_fee", booking.totals.get("renter_fee", "0")),
        )
    )
    expected_charge_cents = int((rental_subtotal + renter_fee_total) * Decimal("100"))
    platform_fee_total = Decimal(booking.totals["platform_fee_total"])
    expected_fee_cents = int(platform_fee_total * Decimal("100"))
    assert charge_call["amount"] == expected_charge_cents
    assert charge_call["currency"] == "cad"
    assert charge_call["metadata"]["kind"] == "booking_charge"
    assert charge_call["capture_method"] == "automatic"
    assert charge_call["automatic_payment_methods"]["enabled"] is True
    assert charge_call["automatic_payment_methods"]["allow_redirects"] == "never"
    assert charge_call["application_fee_amount"] == expected_fee_cents
    assert charge_call["transfer_data"]["destination"] == "acct_test_owner"
    assert charge_call["transfer_group"] == f"booking:{booking.id}"
    assert charge_call["on_behalf_of"] == "acct_test_owner"


def test_create_booking_payment_intents_uses_booking_totals(
    booking_factory,
    monkeypatch,
):
    start = date.today() + timedelta(days=3)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    booking.totals = compute_booking_totals(
        listing=booking.listing,
        start_date=booking.start_date,
        end_date=booking.end_date,
    )
    booking.save(update_fields=["totals"])

    created_calls = []

    def fake_create(**kwargs):
        created_calls.append(kwargs)
        return SimpleNamespace(id=f"pi_{kwargs['metadata']['kind']}")

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "create", fake_create)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", lambda *args, **kwargs: None)

    charge_id = stripe_api.create_booking_charge_intent(
        booking=booking,
        customer_id="cus_test",
        payment_method_id="pm_test",
    )
    deposit_id = stripe_api.create_booking_deposit_hold_intent(
        booking=booking,
        customer_id="cus_test",
        payment_method_id="pm_test",
    )

    assert charge_id == "pi_booking_charge"
    assert deposit_id == "pi_damage_deposit"
    assert len(created_calls) == 2

    rental_subtotal = Decimal(booking.totals["rental_subtotal"])
    renter_fee_total = Decimal(
        booking.totals.get(
            "renter_fee_total",
            booking.totals.get("service_fee", booking.totals.get("renter_fee", "0")),
        )
    )
    expected_charge_cents = int((rental_subtotal + renter_fee_total) * Decimal("100"))
    deposit = Decimal(booking.totals.get("damage_deposit", "0"))
    expected_deposit_cents = int(deposit * Decimal("100"))
    platform_fee_total = Decimal(booking.totals["platform_fee_total"])
    expected_fee_cents = int(platform_fee_total * Decimal("100"))
    charge_call, deposit_call = created_calls
    assert charge_call["amount"] == expected_charge_cents
    assert deposit_call["amount"] == expected_deposit_cents
    assert charge_call["application_fee_amount"] == expected_fee_cents
    assert charge_call["transfer_data"]["destination"] == "acct_test_owner"
    assert deposit_call["application_fee_amount"] == 0
    assert deposit_call["transfer_data"]["destination"] == "acct_test_owner"
    assert deposit_call["transfer_group"] == f"booking:{booking.id}"
    assert deposit_call["on_behalf_of"] == "acct_test_owner"


def test_booking_create_no_deposit_when_zero_damage_deposit(
    renter_user,
    owner_user,
    monkeypatch,
):
    listing = Listing.objects.create(
        owner=owner_user,
        title="Tripod Kit",
        description="Stable tripod",
        daily_price_cad=Decimal("20.00"),
        replacement_value_cad=Decimal("500.00"),
        damage_deposit_cad=Decimal("0.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )
    client = auth(renter_user)
    start = date.today() + timedelta(days=3)
    end = start + timedelta(days=2)

    created_calls = []

    def fake_create(**kwargs):
        created_calls.append(kwargs)
        return SimpleNamespace(id="pi_charge_only")

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "create", fake_create)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", lambda *args, **kwargs: None)

    resp = client.post(
        "/api/bookings/",
        booking_payload(
            listing,
            start,
            end,
            stripe_payment_method_id="pm_789",
        ),
        format="json",
    )

    assert resp.status_code == 201, resp.data
    booking = Booking.objects.get(pk=resp.data["id"])
    assert booking.charge_payment_intent_id == "pi_charge_only"
    assert booking.deposit_hold_id == ""
    assert len(created_calls) == 1


def test_booking_create_card_error_returns_validation_error(renter_user, listing, monkeypatch):
    client = auth(renter_user)
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=3)

    def fail_create(**kwargs):
        raise stripe.error.CardError("Card declined", param=None, code=None)

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "create", fail_create)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", lambda *args, **kwargs: None)

    resp = client.post(
        "/api/bookings/",
        booking_payload(
            listing,
            start,
            end,
            stripe_payment_method_id="pm_456",
        ),
        format="json",
    )

    assert resp.status_code == 400
    assert "non_field_errors" in resp.data
    assert any("card" in msg.lower() for msg in resp.data["non_field_errors"])
    assert Booking.objects.count() == 0


def test_booking_create_transient_error_is_retry_safe(renter_user, listing, monkeypatch):
    client = auth(renter_user)
    start = date.today() + timedelta(days=6)
    end = start + timedelta(days=3)

    created_calls = []
    charge_attempts = {"count": 0}

    def flaky_create(**kwargs):
        created_calls.append(kwargs)
        kind = kwargs["metadata"]["kind"]
        if kind == "booking_charge":
            charge_attempts["count"] += 1
            if charge_attempts["count"] == 1:
                raise stripe.error.APIConnectionError("network issue")
            return SimpleNamespace(id="pi_charge_retry")
        return SimpleNamespace(id="pi_deposit_retry")

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "create", flaky_create)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", lambda *args, **kwargs: None)

    payload = booking_payload(
        listing,
        start,
        end,
        stripe_payment_method_id="pm_retry",
        stripe_customer_id="cus_retry",
    )

    first_resp = client.post("/api/bookings/", payload, format="json")
    assert first_resp.status_code == 400
    assert "Temporary payment issue" in first_resp.data["non_field_errors"][0]
    assert Booking.objects.count() == 0

    second_resp = client.post("/api/bookings/", payload, format="json")
    assert second_resp.status_code == 201, second_resp.data
    booking = Booking.objects.get(pk=second_resp.data["id"])
    assert booking.charge_payment_intent_id == "pi_charge_retry"
    assert booking.deposit_hold_id == ""
    assert booking.renter_stripe_customer_id == "cus_retry"
    assert booking.renter_stripe_payment_method_id == "pm_retry"

    assert len(created_calls) == 2  # one failed charge, one retried charge
    assert created_calls[0]["metadata"]["kind"] == "booking_charge"
    assert created_calls[1]["metadata"]["kind"] == "booking_charge"

    # Charge attempts reuse the same idempotency key for retries and match booking-scoped keys.
    assert created_calls[0]["idempotency_key"] == created_calls[1]["idempotency_key"]
    expected_base = f"booking:{booking.id}:{stripe_api.IDEMPOTENCY_VERSION}"
    totals = booking.totals or {}
    rental_subtotal = Decimal(totals["rental_subtotal"])
    renter_fee_total = Decimal(
        totals.get(
            "renter_fee_total",
            totals.get("service_fee", totals.get("renter_fee", "0")),
        )
    )
    expected_charge_cents = int((rental_subtotal + renter_fee_total) * Decimal("100"))
    platform_fee_total = Decimal(totals["platform_fee_total"])
    expected_fee_cents = int(platform_fee_total * Decimal("100"))
    expected_key = (
        f"{expected_base}:charge_dest_v1:{expected_charge_cents}:"
        f"{expected_fee_cents}:acct_test_owner"
    )
    assert created_calls[1]["idempotency_key"] == expected_key
