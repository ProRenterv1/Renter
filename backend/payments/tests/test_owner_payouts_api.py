"""Tests for owner payouts API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from backend.payments.stripe_api import StripeConfigurationError, StripeTransientError
from bookings.models import Booking
from payments import api as payments_api
from payments.ledger import log_transaction
from payments.models import OwnerPayoutAccount, Transaction

pytestmark = pytest.mark.django_db


def _auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_owner_payouts_summary_returns_balances(owner_user, booking_factory, monkeypatch):
    booking = booking_factory(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=3),
        status=Booking.Status.PAID,
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("120.00"),
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.REFUND,
        amount=Decimal("-20.00"),
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        amount=Decimal("50.00"),
    )

    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_summary_123",
        payouts_enabled=True,
        charges_enabled=True,
        is_fully_onboarded=True,
        requirements_due={
            "currently_due": [],
            "eventually_due": [],
            "past_due": [],
            "disabled_reason": "",
        },
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/summary/")

    assert resp.status_code == 200, resp.data
    connect = resp.data["connect"]
    assert connect["has_account"] is True
    assert connect["stripe_account_id"] == "acct_summary_123"
    assert connect["is_fully_onboarded"] is True
    assert connect["requirements_due"]["disabled_reason"] is None

    balances = resp.data["balances"]
    # OWNER_EARNING 120 + REFUND -20 + DEPOSIT_CAPTURE 50 == 150 net
    assert balances["net_earnings"] == "150.00"
    assert balances["lifetime_gross_earnings"] == "120.00"
    assert balances["lifetime_refunds"] == "-20.00"
    assert balances["lifetime_deposit_captured"] == "50.00"


def test_owner_payouts_summary_handles_stripe_errors(owner_user, monkeypatch):
    monkeypatch.setattr(
        payments_api,
        "ensure_connect_account",
        lambda user: (_ for _ in ()).throw(StripeConfigurationError("missing key")),
    )

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/summary/")

    assert resp.status_code == 200
    assert resp.data["connect"]["has_account"] is False
    assert resp.data["connect"]["stripe_account_id"] is None
    assert resp.data["balances"]["net_earnings"] == "0.00"


def test_owner_payouts_history_returns_paginated_results(owner_user, booking_factory):
    booking = booking_factory(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("25.00"),
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.REFUND,
        amount=Decimal("-5.00"),
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        amount=Decimal("10.00"),
    )

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/history/?limit=2")

    assert resp.status_code == 200, resp.data
    assert resp.data["count"] == 3
    assert resp.data["next_offset"] == 2
    assert len(resp.data["results"]) == 2
    first = resp.data["results"][0]
    assert first["kind"] == Transaction.Kind.DAMAGE_DEPOSIT_RELEASE
    assert first["direction"] == "credit"
    assert first["booking_id"] == booking.id
    assert first["booking_status"] == booking.status
    assert first["listing_title"] == booking.listing.title
    assert first["currency"] == "CAD"

    resp_offset = client.get("/api/owner/payouts/history/?offset=2")
    assert resp_offset.data["next_offset"] is None
    assert len(resp_offset.data["results"]) == 1

    resp_filtered = client.get(f"/api/owner/payouts/history/?kind={Transaction.Kind.REFUND}")
    assert resp_filtered.data["count"] == 1
    assert resp_filtered.data["results"][0]["kind"] == Transaction.Kind.REFUND
    assert resp_filtered.data["results"][0]["direction"] == "debit"


def test_owner_payouts_start_onboarding_returns_link(owner_user, monkeypatch):
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_onboard_123",
        payouts_enabled=False,
        charges_enabled=False,
    )

    monkeypatch.setattr(
        payments_api,
        "create_connect_onboarding_link",
        lambda user: "https://connect.test/onboard",
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/start-onboarding/")

    assert resp.status_code == 200, resp.data
    assert resp.data["onboarding_url"] == "https://connect.test/onboard"
    assert resp.data["stripe_account_id"] == "acct_onboard_123"


def test_owner_payouts_start_onboarding_handles_errors(owner_user, monkeypatch):
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_onboard_err",
        payouts_enabled=False,
        charges_enabled=False,
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    def _raise(_user):
        raise StripeTransientError("stripe down")

    monkeypatch.setattr(payments_api, "create_connect_onboarding_link", _raise)

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/start-onboarding/")

    assert resp.status_code == 503
    assert "detail" in resp.data
