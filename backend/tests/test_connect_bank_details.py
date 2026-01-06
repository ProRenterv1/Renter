import pytest
import stripe
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from payments import api as payments_api
from payments import stripe_api
from payments.api import ONBOARDING_ERROR_MESSAGE
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


# Group A — Successful bank validation
def test_update_bank_details_success(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_key"
    user = User.objects.create_user(username="owner-bank", password="pass1234", can_list=True)
    payout_account = OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_123",
    )

    create_calls = []

    def fake_create_external_account(account_id, external_account):
        create_calls.append((account_id, external_account))
        return {"id": "ba_123", "last4": "4321"}

    monkeypatch.setattr(
        stripe_api.stripe.Account,
        "create_external_account",
        staticmethod(fake_create_external_account),
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda _user: payout_account)

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
    assert payout_account.transit_number == "10010"
    assert payout_account.institution_number == "004"
    assert payout_account.account_number == "4321"
    assert len(create_calls) == 1
    acct_id, external_account = create_calls[0]
    assert acct_id == "acct_123"
    assert external_account["routing_number"] == "00410010"
    assert resp.data["connect"]["bank_details"]["account_last4"] == "4321"


# Group B — Stripe rejects bank details
def test_update_bank_details_invalid(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_key"
    user = User.objects.create_user(username="owner-bank-bad", password="pass1234", can_list=True)
    payout_account = OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_bad",
        transit_number="11111",
        institution_number="000",
        account_number="9999",
    )

    def fake_create_external_account(*args, **kwargs):
        raise stripe.error.InvalidRequestError("Bad routing number", param=None)

    monkeypatch.setattr(
        stripe_api.stripe.Account,
        "create_external_account",
        staticmethod(fake_create_external_account),
    )
    monkeypatch.setattr(payments_api, "ensure_connect_account", lambda _user: payout_account)

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
    assert payout_account.transit_number == "11111"
    assert payout_account.institution_number == "000"
    assert payout_account.account_number == "9999"


# Group C — Connect account missing
def test_update_bank_details_without_connect_account(monkeypatch):
    user = User.objects.create_user(username="owner-bank-none", password="pass1234", can_list=True)

    def fake_ensure(_user):
        raise stripe_api.StripeConfigurationError("missing")

    monkeypatch.setattr(payments_api, "ensure_connect_account", fake_ensure)

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

    assert resp.status_code == 503
    assert resp.data["detail"] == ONBOARDING_ERROR_MESSAGE
