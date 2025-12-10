import pytest
import stripe
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from payments import api as payments_api
from payments import stripe_api
from payments.models import OwnerPayoutAccount

pytestmark = pytest.mark.django_db

User = get_user_model()


def _auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "pass1234"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_update_bank_details_attaches_external_account(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_key"
    user = User.objects.create_user(username="owner", password="pass1234", can_list=True)
    payout_account = OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_123",
    )

    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda _user: payout_account)

    captured = {}

    def fake_create_external_account(account_id, external_account):
        captured["account_id"] = account_id
        captured["external_account"] = external_account
        return {"id": "ba_123", "last4": "6789"}

    monkeypatch.setattr(
        stripe_api.stripe.Account,
        "create_external_account",
        staticmethod(fake_create_external_account),
    )

    client = _auth_client(user)
    resp = client.post(
        "/api/owner/payouts/bank-details/",
        {
            "transit_number": "10010",
            "institution_number": "004",
            "account_number": "000123456789",
        },
        format="json",
    )

    assert resp.status_code == 200, resp.data
    payout_account.refresh_from_db()
    assert captured["account_id"] == payout_account.stripe_account_id
    assert captured["external_account"]["routing_number"] == "00410010"
    assert payout_account.transit_number == "10010"
    assert payout_account.institution_number == "004"
    assert payout_account.account_number == "6789"

    bank_details = resp.data["connect"]["bank_details"]
    assert bank_details["account_last4"] == "6789"
    assert bank_details["transit_number"] == "10010"
    assert bank_details["institution_number"] == "004"


def test_update_bank_details_handles_stripe_error(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_key"
    user = User.objects.create_user(username="owner2", password="pass1234", can_list=True)
    payout_account = OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_err",
        transit_number="old1",
        institution_number="old2",
        account_number="9999",
    )

    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda _user: payout_account)

    def fake_create_external_account(*args, **kwargs):
        raise stripe.error.InvalidRequestError("bad routing", param="routing_number")

    monkeypatch.setattr(
        stripe_api.stripe.Account,
        "create_external_account",
        staticmethod(fake_create_external_account),
    )

    client = _auth_client(user)
    resp = client.post(
        "/api/owner/payouts/bank-details/",
        {
            "transit_number": "10010",
            "institution_number": "004",
            "account_number": "000123456789",
        },
        format="json",
    )

    assert resp.status_code == 400
    assert "Unable to validate bank account" in resp.data["detail"]

    payout_account.refresh_from_db()
    assert payout_account.transit_number == "old1"
    assert payout_account.institution_number == "old2"
    assert payout_account.account_number == "9999"
