from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from bookings.models import Booking
from listings.models import Listing
from listings.services import compute_booking_totals
from payments.models import Transaction

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(username="owner", email="owner@example.com", password="pass123")


@pytest.fixture
def renter_user(db):
    return User.objects.create_user(
        username="renter", email="renter@example.com", password="pass123"
    )


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Test Listing",
        description="For payout tests",
        daily_price_cad=Decimal("120.00"),
        replacement_value_cad=Decimal("500.00"),
        damage_deposit_cad=Decimal("50.00"),
        city="Edmonton",
        postal_code="T5A 0A1",
        is_active=True,
        is_available=True,
    )


@pytest.fixture
def booking_with_totals(settings, owner_user, renter_user, listing):
    settings.BOOKING_RENTER_FEE_RATE = Decimal("0.10")
    settings.BOOKING_OWNER_FEE_RATE = Decimal("0.05")
    settings.STRIPE_SECRET_KEY = "sk_test_key"
    settings.STRIPE_WEBHOOK_SECRET = "whsec_test"
    settings.STRIPE_BOOKINGS_DESTINATION_CHARGES = True

    start = date(2025, 1, 1)
    end = start + timedelta(days=3)
    totals = compute_booking_totals(listing=listing, start_date=start, end_date=end)
    booking = Booking.objects.create(
        listing=listing,
        owner=listing.owner,
        renter=renter_user,
        start_date=start,
        end_date=end,
        status=Booking.Status.CONFIRMED,
        totals=totals,
        charge_payment_intent_id="",
    )
    owner_payout = Decimal(totals["owner_payout"])
    return booking, owner_payout


def _webhook_payload(booking: Booking) -> dict:
    return {
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_123",
                "metadata": {
                    "kind": "booking_charge",
                    "booking_id": str(booking.id),
                    "listing_id": str(booking.listing_id),
                    "env": "dev",
                },
            }
        },
    }


@pytest.mark.django_db
@patch("payments.stripe_api.stripe.Transfer.create")
def test_owner_transfer_created_on_webhook(
    mock_transfer_create,
    booking_with_totals,
    owner_user,
    settings,
    monkeypatch,
):
    booking, owner_payout = booking_with_totals
    platform_user = User.objects.create_user(
        username="platform-ledger",
        email="platform@example.com",
        password="pass123",
    )
    settings.PLATFORM_LEDGER_USER_ID = platform_user.id
    mock_transfer_create.return_value = {"id": "tr_test_123"}

    event_payload = _webhook_payload(booking)
    monkeypatch.setattr(
        "payments.stripe_api.stripe.Webhook.construct_event",
        lambda payload, sig_header, secret: event_payload,
    )
    monkeypatch.setattr(
        "payments.stripe_api._get_stripe_api_key",
        lambda: "sk_test_key",
    )
    monkeypatch.setattr(
        "payments.stripe_api.stripe.PaymentIntent.retrieve",
        lambda _intent_id, **_kwargs: SimpleNamespace(
            charges=SimpleNamespace(data=[SimpleNamespace(transfer="tr_transfer_123")])
        ),
    )

    client = APIClient()
    response = client.post(
        "/api/payments/stripe/webhook/",
        data=json.dumps(event_payload),
        content_type="application/json",
        HTTP_STRIPE_SIGNATURE="test_sig",
    )
    assert response.status_code == 200

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PAID
    assert booking.charge_payment_intent_id == "pi_test_123"

    owner_txn = Transaction.objects.get(
        user=booking.listing.owner,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
    )
    assert owner_txn.amount == owner_payout
    assert owner_txn.stripe_id == "tr_transfer_123"

    platform_txn = Transaction.objects.get(
        user=platform_user,
        booking=booking,
        kind=Transaction.Kind.PLATFORM_FEE,
    )
    platform_fee_total = Decimal(booking.totals["platform_fee_total"])
    assert platform_txn.amount == platform_fee_total

    mock_transfer_create.assert_not_called()


@pytest.mark.django_db
@patch("payments.stripe_api.stripe.Transfer.create")
def test_owner_transfer_webhook_idempotent(
    mock_transfer_create,
    booking_with_totals,
    owner_user,
    settings,
    monkeypatch,
):
    booking, _owner_payout = booking_with_totals
    platform_user = User.objects.create_user(
        username="platform-ledger-2",
        email="platform2@example.com",
        password="pass123",
    )
    settings.PLATFORM_LEDGER_USER_ID = platform_user.id
    mock_transfer_create.return_value = {"id": "tr_test_123"}

    event_payload = _webhook_payload(booking)
    monkeypatch.setattr(
        "payments.stripe_api.stripe.Webhook.construct_event",
        lambda payload, sig_header, secret: event_payload,
    )
    monkeypatch.setattr(
        "payments.stripe_api._get_stripe_api_key",
        lambda: "sk_test_key",
    )
    monkeypatch.setattr(
        "payments.stripe_api.stripe.PaymentIntent.retrieve",
        lambda _intent_id, **_kwargs: SimpleNamespace(
            charges=SimpleNamespace(data=[SimpleNamespace(transfer="tr_transfer_123")])
        ),
    )

    client = APIClient()
    for _ in range(2):
        response = client.post(
            "/api/payments/stripe/webhook/",
            data=json.dumps(event_payload),
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="test_sig",
        )
        assert response.status_code == 200

    txs = Transaction.objects.filter(
        user=booking.listing.owner,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
    )
    assert txs.count() == 1

    platform_txs = Transaction.objects.filter(
        user=platform_user,
        booking=booking,
        kind=Transaction.Kind.PLATFORM_FEE,
    )
    assert platform_txs.count() == 1

    mock_transfer_create.assert_not_called()
