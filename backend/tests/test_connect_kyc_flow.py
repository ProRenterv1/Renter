import pytest
import stripe
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from identity.models import IdentityVerification, is_user_identity_verified
from payments import stripe_api
from payments.models import OwnerPayoutAccount

pytestmark = pytest.mark.django_db

User = get_user_model()


def _auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "StrongPass123!"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class AnyDict(dict):
    """Helper to allow isinstance checks on monkeypatched call payloads."""


# Group A — Auto create Connect account on signup
def test_signup_creates_connect_account(monkeypatch, settings):
    settings.CONNECT_BUSINESS_NAME = "Kitoro QA"
    settings.CONNECT_BUSINESS_URL = "https://example.test"
    settings.CONNECT_BUSINESS_PRODUCT_DESCRIPTION = "Test desc"
    settings.CONNECT_BUSINESS_MCC = "1234"

    created_calls = []

    monkeypatch.setattr(stripe_api, "_get_stripe_api_key", lambda: "sk_test_key")

    base_payload = {
        "id": "acct_123",
        "charges_enabled": False,
        "payouts_enabled": False,
        "requirements": {
            "currently_due": [],
            "eventually_due": [],
            "past_due": [],
            "disabled_reason": "",
        },
        "individual": {},
        "external_accounts": {"data": []},
    }

    def fake_create(**kwargs):
        created_calls.append(kwargs)
        return base_payload

    monkeypatch.setattr(
        stripe_api,
        "_retrieve_account_with_expand",
        lambda _account_id: base_payload,
    )
    monkeypatch.setattr(stripe.Account, "modify", staticmethod(lambda *a, **k: base_payload))
    monkeypatch.setattr(stripe.Account, "create", staticmethod(fake_create))

    client = APIClient()
    payload = {
        "username": "owner-signup",
        "email": "owner@example.com",
        "password": "StrongPass123!",
        "first_name": "Owner",
        "last_name": "Example",
        "can_list": True,
    }
    resp = client.post("/api/users/signup/", payload, format="json")

    assert resp.status_code == 201, resp.data
    user = User.objects.get(username="owner-signup")
    payout = OwnerPayoutAccount.objects.get(user=user)
    assert payout.stripe_account_id == "acct_123"
    assert len(created_calls) == 1
    create_kwargs = created_calls[0]
    business_profile = create_kwargs["business_profile"]
    assert business_profile["name"] == settings.CONNECT_BUSINESS_NAME
    assert business_profile["product_description"] == settings.CONNECT_BUSINESS_PRODUCT_DESCRIPTION
    assert business_profile["url"] == settings.CONNECT_BUSINESS_URL
    assert business_profile["mcc"] == settings.CONNECT_BUSINESS_MCC
    individual = create_kwargs["individual"]
    assert individual["first_name"] == payload["first_name"]
    assert individual["last_name"] == payload["last_name"]
    assert individual["email"] == payload["email"]


def test_signup_continues_if_stripe_fails(monkeypatch):
    monkeypatch.setattr(stripe_api, "_get_stripe_api_key", lambda: "sk_test_key")

    def fake_create(**_kwargs):
        raise stripe.error.InvalidRequestError("bad request", param="test")

    monkeypatch.setattr(stripe.Account, "create", staticmethod(fake_create))

    client = APIClient()
    payload = {
        "username": "owner-fail",
        "email": "owner-fail@example.com",
        "password": "StrongPass123!",
        "first_name": "Owner",
        "last_name": "Fail",
        "can_list": True,
    }
    resp = client.post("/api/users/signup/", payload, format="json")

    assert resp.status_code == 201, resp.data
    user = User.objects.get(username="owner-fail")
    assert not OwnerPayoutAccount.objects.filter(user=user).exists()


# Group B — Connect-only KYC logic
def test_identity_verified_when_connect_onboarded():
    user = User.objects.create_user(
        username="kyc-verified",
        email="v@example.com",
        password="StrongPass123!",
        can_list=True,
        can_rent=True,
    )
    OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_verified",
        is_fully_onboarded=True,
        payouts_enabled=True,
        charges_enabled=True,
    )

    client = _auth_client(user)
    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is True
    assert resp.data["latest"]["status"] == "verified"
    assert is_user_identity_verified(user) is True


def test_identity_not_verified_when_connect_not_onboarded():
    user = User.objects.create_user(
        username="kyc-pending",
        email="p@example.com",
        password="StrongPass123!",
        can_list=True,
        can_rent=True,
    )
    OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_pending",
        is_fully_onboarded=False,
        payouts_enabled=False,
        charges_enabled=False,
    )

    client = _auth_client(user)
    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is False
    assert resp.data["latest"]["status"] == "pending"
    assert is_user_identity_verified(user) is False


def test_identity_not_verified_if_no_payout_account():
    user = User.objects.create_user(
        username="kyc-none",
        email="n@example.com",
        password="StrongPass123!",
        can_list=True,
        can_rent=True,
    )

    client = _auth_client(user)
    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is False
    assert resp.data["latest"] is None
    assert is_user_identity_verified(user) is False


# Group C — identity_start deprecated
def test_identity_start_returns_error(monkeypatch):
    user = User.objects.create_user(
        username="kyc-start",
        email="s@example.com",
        password="StrongPass123!",
        can_list=True,
        can_rent=True,
    )
    client = _auth_client(user)

    resp = client.post("/api/identity/start/")
    assert resp.status_code == 400
    assert "Stripe Connect onboarding" in resp.data["detail"]


def test_account_updated_syncs_profile_and_bank_details():
    user = User.objects.create_user(
        username="kyc-sync",
        email="sync@example.com",
        password="StrongPass123!",
        can_list=True,
        can_rent=True,
    )
    payout_account = OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_sync",
    )

    account_payload = {
        "id": "acct_sync",
        "charges_enabled": True,
        "payouts_enabled": True,
        "requirements": {
            "currently_due": [],
            "eventually_due": [],
            "past_due": [],
            "disabled_reason": None,
        },
        "individual": {
            "phone": "+15555550123",
            "dob": {"day": 2, "month": 3, "year": 1990},
            "address": {
                "line1": "123 King St",
                "city": "Toronto",
                "state": "on",
                "postal_code": "m5v 0e9",
            },
        },
        "external_accounts": {
            "data": [
                {
                    "object": "bank_account",
                    "default_for_currency": True,
                    "routing_number": "00412345",
                    "last4": "6789",
                }
            ]
        },
    }

    stripe_api._handle_connect_account_updated_event(account_payload)

    user.refresh_from_db()
    payout_account.refresh_from_db()
    assert user.phone == "+15555550123"
    assert user.birth_date.isoformat() == "1990-03-02"
    assert user.street_address == "123 King St"
    assert user.city == "Toronto"
    assert user.province == "ON"
    assert user.postal_code == "M5V 0E9"
    assert payout_account.institution_number == "004"
    assert payout_account.transit_number == "12345"
    assert payout_account.account_number == "6789"
    assert payout_account.last_synced_at is not None
    verification = IdentityVerification.objects.filter(user=user, session_id="acct_sync").first()
    assert verification is not None
    assert verification.status == IdentityVerification.Status.VERIFIED


def test_account_updated_fetches_expanded_account(monkeypatch):
    user = User.objects.create_user(
        username="kyc-expand",
        email="expand@example.com",
        password="StrongPass123!",
        can_list=True,
        can_rent=True,
    )
    OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_expand",
    )

    # Payload missing nested fields to force a re-fetch with expand
    incoming_payload = {"id": "acct_expand"}

    monkeypatch.setattr(stripe_api, "_get_stripe_api_key", lambda: "sk_test_key")

    fetched_payload = {
        "id": "acct_expand",
        "charges_enabled": True,
        "payouts_enabled": True,
        "requirements": {
            "currently_due": [],
            "eventually_due": [],
            "past_due": [],
            "disabled_reason": "",
        },
        "individual": {
            "phone": "+12223334444",
            "dob": {"day": 5, "month": 6, "year": 1985},
            "address": {
                "line1": "789 Queen St",
                "city": "Vancouver",
                "state": "BC",
                "postal_code": "v5k 0a1",
            },
        },
        "external_accounts": {
            "data": [
                {
                    "object": "bank_account",
                    "default_for_currency": True,
                    "routing_number": "123456789",
                    "last4": "1111",
                }
            ]
        },
    }

    retrieve_calls: list[dict] = []

    def fake_retrieve(account_id, expand=None):
        retrieve_calls.append({"account_id": account_id, "expand": expand})
        return fetched_payload

    monkeypatch.setattr(stripe_api.stripe.Account, "retrieve", staticmethod(fake_retrieve))

    stripe_api._handle_connect_account_updated_event(incoming_payload)

    user.refresh_from_db()
    payout = OwnerPayoutAccount.objects.get(user=user)

    assert retrieve_calls, "Should fetch expanded account when payload is incomplete"
    assert user.phone == "+12223334444"
    assert user.birth_date.isoformat() == "1985-06-05"
    assert user.city == "Vancouver"
    assert user.province == "BC"
    assert user.postal_code == "V5K 0A1"
    assert payout.transit_number == "45678"
    assert payout.institution_number == "123"
    assert payout.account_number == "1111"
