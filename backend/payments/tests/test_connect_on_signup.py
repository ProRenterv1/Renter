import pytest
from django.contrib.auth import get_user_model

from payments import stripe_api
from payments.models import OwnerPayoutAccount

pytestmark = pytest.mark.django_db


def test_connect_account_created_on_signup(api_client, monkeypatch, settings):
    settings.CONNECT_BUSINESS_NAME = "Renter QA"
    settings.CONNECT_BUSINESS_URL = "https://platform.test"
    settings.CONNECT_BUSINESS_PRODUCT_DESCRIPTION = "Test rentals"
    settings.CONNECT_BUSINESS_MCC = "7399"

    create_calls = []

    monkeypatch.setattr(stripe_api, "_get_stripe_api_key", lambda: "sk_test")

    def _fake_create(**kwargs):
        create_calls.append(kwargs)
        return {
            "id": "acct_signup_123",
            "charges_enabled": False,
            "payouts_enabled": False,
            "requirements": {
                "currently_due": [],
                "eventually_due": [],
                "past_due": [],
                "disabled_reason": "",
            },
        }

    monkeypatch.setattr(stripe_api.stripe.Account, "create", _fake_create)

    payload = {
        "username": "owner-signup",
        "email": "owner@example.com",
        "password": "StrongPass123!",
        "first_name": "Owner",
        "last_name": "Example",
        "can_list": True,
    }

    resp = api_client.post("/api/users/signup/", payload, format="json")
    assert resp.status_code == 201, resp.data

    user = get_user_model().objects.get(username=payload["username"])
    payout_account = OwnerPayoutAccount.objects.get(user=user)
    assert payout_account.stripe_account_id == "acct_signup_123"

    assert create_calls, "Stripe Account.create was not invoked"
    create_kwargs = create_calls[0]
    business_profile = create_kwargs["business_profile"]
    assert business_profile["name"] == settings.CONNECT_BUSINESS_NAME
    assert business_profile["product_description"] == settings.CONNECT_BUSINESS_PRODUCT_DESCRIPTION
    assert business_profile["url"] == settings.CONNECT_BUSINESS_URL
    assert business_profile["mcc"] == settings.CONNECT_BUSINESS_MCC

    individual = create_kwargs["individual"]
    assert individual["first_name"] == payload["first_name"]
    assert individual["last_name"] == payload["last_name"]
    assert individual["email"] == payload["email"]
    assert create_kwargs["metadata"]["user_id"] == str(user.id)


def test_signup_succeeds_when_connect_fails(api_client, monkeypatch):
    def _raise(_user):
        raise stripe_api.StripeConfigurationError("missing stripe key")

    monkeypatch.setattr("payments.stripe_api.ensure_connect_account", _raise)

    payload = {
        "username": "owner-no-connect",
        "email": "owner2@example.com",
        "password": "StrongPass123!",
        "first_name": "Owner",
        "last_name": "Fallback",
        "can_list": True,
    }

    resp = api_client.post("/api/users/signup/", payload, format="json")
    assert resp.status_code == 201, resp.data

    user = get_user_model().objects.get(username=payload["username"])
    assert not OwnerPayoutAccount.objects.filter(user=user).exists()
