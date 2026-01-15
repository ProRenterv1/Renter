"""Tests for owner payouts API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
import stripe
from rest_framework.test import APIClient

from backend.payments.stripe_api import StripeConfigurationError, StripeTransientError
from bookings.models import Booking
from core.settings_resolver import clear_settings_cache
from operator_settings.models import DbSetting
from payments import api as payments_api
from payments import stripe_api
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


@pytest.mark.parametrize(
    ("method", "url"),
    [
        ("get", "/api/owner/payouts/summary/"),
        ("get", "/api/owner/payouts/history/"),
        ("post", "/api/owner/payouts/start-onboarding/"),
        ("post", "/api/owner/payouts/bank-details/"),
        ("post", "/api/owner/payouts/instant-payout/"),
    ],
)
def test_owner_payouts_endpoints_require_authentication(method, url):
    client = APIClient()
    response = getattr(client, method)(url, format="json")
    assert response.status_code == 401


def test_owner_payouts_summary_returns_balances(owner_user, booking_factory, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
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
        transit_number="12345",
        institution_number="678",
        account_number="000123456789",
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test_summary")

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/summary/")

    assert resp.status_code == 200, resp.data
    connect = resp.data["connect"]
    assert connect["has_account"] is True
    assert connect["stripe_account_id"] == "acct_summary_123"
    assert connect["is_fully_onboarded"] is True
    assert connect["requirements_due"]["disabled_reason"] is None
    assert connect["bank_details"]["account_last4"] == "6789"
    assert connect["bank_details"]["transit_number"] == "12345"
    assert connect["bank_details"]["institution_number"] == "678"
    kyc_steps = connect["kyc_steps"]
    assert kyc_steps["personal_complete"] is True
    assert kyc_steps["id_required"] is False
    assert kyc_steps["id_submitted_pending"] is False
    assert kyc_steps["kyc_locked"] is False
    assert kyc_steps["personal_due"] == []
    assert kyc_steps["id_due"] == []

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
    assert resp.data["connect"]["bank_details"] is None
    assert resp.data["connect"]["kyc_steps"]["personal_complete"] is False
    assert resp.data["connect"]["kyc_steps"]["id_required"] is False
    assert resp.data["connect"]["kyc_steps"]["id_submitted_pending"] is False
    assert resp.data["connect"]["kyc_steps"]["kyc_locked"] is False
    assert resp.data["connect"]["kyc_steps"]["personal_due"] == []
    assert resp.data["connect"]["kyc_steps"]["id_due"] == []
    assert resp.data["balances"]["net_earnings"] == "0.00"


@pytest.mark.parametrize(
    ("requirements_due", "is_fully_onboarded", "expected"),
    [
        (
            {
                "currently_due": ["individual.first_name", "external_account"],
                "eventually_due": [],
                "past_due": [],
                "disabled_reason": "",
            },
            False,
            {
                "personal_complete": False,
                "id_required": False,
                "id_submitted_pending": False,
                "kyc_locked": False,
                "personal_due": ["external_account", "individual.first_name"],
                "id_due": [],
            },
        ),
        (
            {
                "currently_due": [],
                "eventually_due": [],
                "past_due": ["individual.verification.additional_document"],
                "disabled_reason": "",
            },
            False,
            {
                "personal_complete": True,
                "id_required": True,
                "id_submitted_pending": False,
                "kyc_locked": False,
                "personal_due": [],
                "id_due": ["individual.verification.additional_document"],
            },
        ),
        (
            {
                "currently_due": [],
                "eventually_due": [],
                "past_due": [],
                "disabled_reason": None,
            },
            False,
            {
                "personal_complete": True,
                "id_required": False,
                "id_submitted_pending": True,
                "kyc_locked": True,
                "personal_due": [],
                "id_due": [],
            },
        ),
        (
            {
                "currently_due": [],
                "eventually_due": [],
                "past_due": [],
                "disabled_reason": None,
            },
            True,
            {
                "personal_complete": True,
                "id_required": False,
                "id_submitted_pending": False,
                "kyc_locked": False,
                "personal_due": [],
                "id_due": [],
            },
        ),
    ],
)
def test_owner_payouts_summary_includes_kyc_steps(
    owner_user, monkeypatch, requirements_due, is_fully_onboarded, expected
):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_steps_123",
        requirements_due=requirements_due,
        is_fully_onboarded=is_fully_onboarded,
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr(payments_api, "get_connect_available_balance", lambda account: None)

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/summary/")

    assert resp.status_code == 200, resp.data
    steps = resp.data["connect"]["kyc_steps"]
    assert steps["personal_complete"] is expected["personal_complete"]
    assert steps["id_required"] is expected["id_required"]
    assert steps["id_submitted_pending"] is expected["id_submitted_pending"]
    assert steps["kyc_locked"] is expected["kyc_locked"]
    assert steps.get("personal_due") == expected["personal_due"]
    assert steps.get("id_due") == expected["id_due"]


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


def test_owner_payouts_history_includes_booking_charge_with_all_scope(
    owner_user,
    booking_factory,
):
    booking = booking_factory(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        amount=Decimal("120.00"),
    )

    client = _auth_client(owner_user)
    resp = client.get("/api/owner/payouts/history/?scope=all")

    assert resp.status_code == 200, resp.data
    kinds = [row["kind"] for row in resp.data["results"]]
    assert Transaction.Kind.BOOKING_CHARGE in kinds

    charge_row = next(
        row for row in resp.data["results"] if row["kind"] == Transaction.Kind.BOOKING_CHARGE
    )
    assert charge_row["amount"] == "-120.00"
    assert charge_row["direction"] == "debit"


def test_owner_payouts_start_onboarding_embedded_mode(owner_user, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_onboard_123",
    )

    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test_embed")
    monkeypatch.setattr(
        "payments.stripe_api.ensure_connect_account",
        lambda user, business_type=None: payout_account,
    )
    monkeypatch.setattr(
        "payments.stripe_api.sync_connect_account_personal_info",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        stripe_api.stripe.AccountSession,
        "create",
        staticmethod(
            lambda **kwargs: {"client_secret": "sess_secret_123", "expires_at": 1_700_000_000}
        ),
    )
    monkeypatch.setattr(
        "payments.stripe_api.create_connect_onboarding_link",
        lambda *args, **kwargs: "https://connect.test/onboard",
    )

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/start-onboarding/")

    assert resp.status_code == 200, resp.data
    assert resp.data["client_secret"] == "sess_secret_123"
    assert resp.data["stripe_account_id"] == payout_account.stripe_account_id
    assert resp.data["onboarding_url"] == "https://connect.test/onboard"
    assert resp.data["mode"] == "embedded"
    assert isinstance(resp.data["expires_at"], str)
    assert resp.data["expires_at"].endswith("Z")


def test_owner_payouts_start_onboarding_session_failure_falls_back(owner_user, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_onboard_fallback",
    )

    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test_fallback")
    monkeypatch.setattr(
        "payments.stripe_api.ensure_connect_account",
        lambda user, business_type=None: payout_account,
    )
    monkeypatch.setattr(
        "payments.stripe_api.sync_connect_account_personal_info",
        lambda *args, **kwargs: None,
    )

    def raise_session(**kwargs):
        raise stripe.error.APIConnectionError("session unavailable", param=None)

    monkeypatch.setattr(
        stripe_api.stripe.AccountSession,
        "create",
        staticmethod(raise_session),
    )
    monkeypatch.setattr(
        "payments.stripe_api.create_connect_onboarding_link",
        lambda *args, **kwargs: "https://connect.test/onboard-fallback",
    )

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/start-onboarding/")

    assert resp.status_code == 200, resp.data
    assert resp.data["client_secret"] is None
    assert resp.data["onboarding_url"] == "https://connect.test/onboard-fallback"
    assert resp.data["mode"] == "hosted_fallback"
    assert resp.data["stripe_account_id"] == payout_account.stripe_account_id


def test_owner_payouts_start_onboarding_prefill_permission_denied_is_nonfatal(
    owner_user, monkeypatch
):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_prefill_perm",
    )

    monkeypatch.setattr("payments.stripe_api._get_stripe_api_key", lambda: "sk_test_perm")
    monkeypatch.setattr(
        "payments.stripe_api.ensure_connect_account",
        lambda user, business_type=None: payout_account,
    )

    def permission_error(*args, **kwargs):
        raise stripe.error.PermissionError(
            "denied",
            param=None,
            code="permission_denied",
            http_status=403,
            request_id="req_denied",
        )

    monkeypatch.setattr(stripe_api.stripe.Account, "modify", staticmethod(permission_error))
    monkeypatch.setattr(
        stripe_api.stripe.AccountSession,
        "create",
        staticmethod(
            lambda **kwargs: {"client_secret": "sess_secret_perm", "expires_at": 1_800_000_000}
        ),
    )
    monkeypatch.setattr(
        "payments.stripe_api.create_connect_onboarding_link",
        lambda *args, **kwargs: "https://connect.test/onboard-perm",
    )

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/start-onboarding/")

    assert resp.status_code == 200, resp.data
    assert resp.data["client_secret"] == "sess_secret_perm"
    assert resp.data["mode"] == "embedded"
    assert resp.data["onboarding_url"] == "https://connect.test/onboard-perm"


def test_owner_payouts_start_onboarding_passes_business_type(owner_user, monkeypatch):
    captured: dict[str, str | None] = {}
    payload = {
        "client_secret": "sess_secret_company",
        "stripe_account_id": "acct_company_123",
        "expires_at": "2023-11-14T22:13:20Z",
        "onboarding_url": "https://connect.test/onboard-company",
        "mode": "embedded",
    }

    def fake_session(user, business_type=None):
        captured["business_type"] = business_type
        return payload

    monkeypatch.setattr(payments_api, "create_connect_onboarding_session", fake_session)

    client = _auth_client(owner_user)
    resp = client.post(
        "/api/owner/payouts/start-onboarding/",
        {"business_type": "company"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert captured["business_type"] == "company"
    assert resp.data["stripe_account_id"] == payload["stripe_account_id"]
    assert resp.data["mode"] == "embedded"


def test_owner_payouts_start_onboarding_rejects_invalid_business_type(owner_user):
    client = _auth_client(owner_user)
    resp = client.post(
        "/api/owner/payouts/start-onboarding/",
        {"business_type": "not-a-valid-choice"},
        format="json",
    )

    assert resp.status_code == 400
    assert "business_type" in resp.data


def test_owner_payouts_start_onboarding_handles_errors(owner_user, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()

    def _raise(_user):
        raise StripeTransientError("stripe down")

    monkeypatch.setattr(payments_api, "create_connect_onboarding_session", _raise)

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/start-onboarding/")

    assert resp.status_code == 503
    assert "detail" in resp.data


def test_owner_payouts_update_bank_details(owner_user, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_bank_123",
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr(
        payments_api,
        "update_connect_bank_account",
        lambda **kwargs: {"id": "ba_test", "last4": "4567"},
    )

    client = _auth_client(owner_user)
    resp = client.post(
        "/api/owner/payouts/bank-details/",
        {
            "transit_number": "10010",
            "institution_number": "004",
            "account_number": "1234567",
        },
        format="json",
    )

    assert resp.status_code == 200, resp.data
    payout_account.refresh_from_db()
    assert payout_account.transit_number == "10010"
    assert payout_account.institution_number == "004"
    assert payout_account.account_number == "4567"
    connect = resp.data["connect"]
    assert connect["bank_details"]["account_last4"] == "4567"
    assert connect["bank_details"]["transit_number"] == "10010"
    assert connect["bank_details"]["institution_number"] == "004"


def test_history_for_renter_excludes_deposit_capture_and_signs_charge_negative(
    renter_user,
    booking_factory,
):
    booking = booking_factory(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    log_transaction(
        user=renter_user,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        amount=Decimal("165.00"),
    )
    log_transaction(
        user=renter_user,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        amount=Decimal("250.00"),
    )
    log_transaction(
        user=renter_user,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        amount=Decimal("250.00"),
    )

    client = _auth_client(renter_user)
    resp = client.get("/api/owner/payouts/history/")

    assert resp.status_code == 200, resp.data
    kinds = [row["kind"] for row in resp.data["results"]]
    assert Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE not in kinds
    assert Transaction.Kind.BOOKING_CHARGE in kinds

    charge_row = next(
        row for row in resp.data["results"] if row["kind"] == Transaction.Kind.BOOKING_CHARGE
    )
    assert charge_row["amount"] == "-165.00"
    assert charge_row["direction"] == "debit"

    release_row = next(
        row
        for row in resp.data["results"]
        if row["kind"] == Transaction.Kind.DAMAGE_DEPOSIT_RELEASE
    )
    assert release_row["amount"] == "250.00"
    assert release_row["direction"] == "credit"


def test_owner_payouts_update_bank_details_requires_fields(owner_user, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_bank_req",
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/bank-details/", {}, format="json")

    assert resp.status_code == 400
    assert "transit_number" in resp.data
    assert "institution_number" in resp.data
    assert "account_number" in resp.data


def test_owner_payouts_instant_payout_preview(owner_user, booking_factory, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    booking = booking_factory(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=2),
        status=Booking.Status.PAID,
    )
    DbSetting.objects.create(
        key="ORG_GST_NUMBER",
        value_json="123456789RT0001",
        value_type="str",
    )
    DbSetting.objects.create(
        key="ORG_GST_REGISTERED",
        value_json=True,
        value_type="bool",
    )
    clear_settings_cache()
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("150.00"),
    )
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_instant_preview",
        transit_number="10010",
        institution_number="004",
        account_number="000012345678",
        lifetime_instant_payouts=Decimal("0.00"),
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/instant-payout/", {}, format="json")

    assert resp.status_code == 200, resp.data
    assert resp.data["executed"] is False
    assert resp.data["currency"] == "cad"
    assert resp.data["amount_before_fee"] == "150.00"
    assert resp.data["fee_base"] == "4.50"
    assert resp.data["fee_gst"] == "0.23"
    assert resp.data["amount_after_fee"] == "145.27"
    payout_account.refresh_from_db()
    assert payout_account.lifetime_instant_payouts == Decimal("0.00")


def test_owner_payouts_instant_payout_requires_bank_details(owner_user, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_instant_missing",
        transit_number="",
        institution_number="",
        account_number="000000000001",
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    client = _auth_client(owner_user)
    resp = client.post("/api/owner/payouts/instant-payout/", {}, format="json")

    assert resp.status_code == 400
    assert "detail" in resp.data


def test_owner_payouts_instant_payout_executes_and_logs(owner_user, booking_factory, monkeypatch):
    OwnerPayoutAccount.objects.filter(user=owner_user).delete()
    booking = booking_factory(
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    DbSetting.objects.create(
        key="ORG_GST_NUMBER",
        value_json="123456789RT0001",
        value_type="str",
    )
    DbSetting.objects.create(
        key="ORG_GST_REGISTERED",
        value_json=True,
        value_type="bool",
    )
    clear_settings_cache()
    log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("200.00"),
    )
    payout_account = OwnerPayoutAccount.objects.create(
        user=owner_user,
        stripe_account_id="acct_instant_exec",
        transit_number="10010",
        institution_number="004",
        account_number="000012345678",
        lifetime_instant_payouts=Decimal("50.00"),
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda user: payout_account)

    captured_call = {}
    captured_fee_transfer = {}

    def _fake_create_instant_payout(**kwargs):
        captured_call.update(kwargs)
        return SimpleNamespace(id="po_test_123")

    monkeypatch.setattr(payments_api, "create_instant_payout", _fake_create_instant_payout)

    def _fake_transfer_earnings_to_platform(**kwargs):
        captured_fee_transfer.update(kwargs)
        return "tr_fee_123"

    monkeypatch.setattr(
        payments_api, "transfer_earnings_to_platform", _fake_transfer_earnings_to_platform
    )

    client = _auth_client(owner_user)
    resp = client.post(
        "/api/owner/payouts/instant-payout/",
        {"confirm": True},
        format="json",
    )

    assert resp.status_code == 202, resp.data
    assert resp.data["executed"] is True
    assert resp.data["stripe_payout_id"] == "po_test_123"
    assert resp.data["amount_before_fee"] == "200.00"
    assert resp.data["fee_base"] == "6.00"
    assert resp.data["fee_gst"] == "0.30"
    assert resp.data["amount_after_fee"] == "193.70"
    assert captured_call["amount_cents"] == 19370
    assert captured_call["metadata"]["amount_before_fee"] == "200.00"
    assert captured_call["user"] == owner_user
    assert captured_call["payout_account"] == payout_account
    assert captured_fee_transfer["payout_account"] == payout_account
    assert captured_fee_transfer["amount_cents"] == 630
    assert captured_fee_transfer["metadata"]["kind"] == "instant_payout_fee"
    assert captured_fee_transfer["metadata"]["payout_id"] == "po_test_123"
    assert captured_fee_transfer["metadata"]["amount_before_fee"] == "200.00"
    assert captured_fee_transfer["metadata"]["amount_after_fee"] == "193.70"
    assert captured_fee_transfer["metadata"]["fee_base"] == "6.00"
    assert captured_fee_transfer["metadata"]["fee_gst"] == "0.30"
    assert captured_fee_transfer["metadata"]["fee_total"] == "6.30"

    payout_account.refresh_from_db()
    assert payout_account.lifetime_instant_payouts == Decimal("250.00")

    earnings = Transaction.objects.filter(user=owner_user, kind=Transaction.Kind.OWNER_EARNING)
    assert earnings.filter(amount=Decimal("200.00")).exists()
    payouts = Transaction.objects.filter(user=owner_user, kind=Transaction.Kind.OWNER_PAYOUT)
    assert payouts.filter(amount=Decimal("-200.00")).exists()
    fee_txn = Transaction.objects.get(user=owner_user, kind=Transaction.Kind.PLATFORM_FEE)
    assert fee_txn.amount == Decimal("6.00")
    assert fee_txn.stripe_id == "tr_fee_123"
    gst_txn = Transaction.objects.get(user=owner_user, kind=Transaction.Kind.GST_COLLECTED)
    assert gst_txn.amount == Decimal("0.30")
