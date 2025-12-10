import pytest
from django.contrib.auth import get_user_model

from payments import stripe_api
from payments.models import OwnerPayoutAccount

pytestmark = pytest.mark.django_db
Call = dict


def test_connect_account_created_on_signup(api_client, monkeypatch, settings):
    settings.CONNECT_BUSINESS_NAME = "Renter QA"
    settings.CONNECT_BUSINESS_URL = "https://platform.test"
    settings.CONNECT_BUSINESS_PRODUCT_DESCRIPTION = "Test rentals"
    settings.CONNECT_BUSINESS_MCC = "7399"

    create_calls = []

    monkeypatch.setattr(stripe_api, "_get_stripe_api_key", lambda: "sk_test")

    base_payload = {
        "id": "acct_signup_123",
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

    def _fake_create(**kwargs):
        create_calls.append(kwargs)
        return base_payload

    monkeypatch.setattr(stripe_api.stripe.Account, "modify", staticmethod(lambda *a, **k: {}))
    monkeypatch.setattr(
        stripe_api,
        "_retrieve_account_with_expand",
        lambda _account_id: base_payload,
    )
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
    assert individual["relationship"]["title"] == "Renter"
    assert create_kwargs["metadata"]["user_id"] == str(user.id)
    assert create_kwargs["metadata"]["job_title"] == "Renter"


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


def test_onboarding_prefills_personal_info(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_key"
    user = get_user_model().objects.create_user(
        username="prefill",
        email="prefill@example.com",
        password="Secret123!",
        first_name="Prefill",
        last_name="Owner",
        can_list=True,
    )
    payout = OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_prefill",
    )

    account_payload = {
        "id": payout.stripe_account_id,
        "charges_enabled": False,
        "payouts_enabled": False,
        "requirements": {
            "currently_due": [],
            "eventually_due": [],
            "past_due": [],
            "disabled_reason": "",
        },
        "individual": {"phone": "", "address": {}, "dob": {}},
        "external_accounts": {"data": []},
    }

    calls: list[Call] = []

    monkeypatch.setattr(stripe_api, "_get_stripe_api_key", lambda: "sk_test_key")
    monkeypatch.setattr(
        stripe_api,
        "_retrieve_account_with_expand",
        lambda _account_id: account_payload,
    )
    monkeypatch.setattr(
        stripe_api.stripe.Account, "modify", staticmethod(lambda *a, **k: account_payload)
    )
    monkeypatch.setattr(
        stripe_api.stripe.Account, "retrieve", staticmethod(lambda *a, **k: account_payload)
    )

    def fake_account_link_create(**kwargs):
        calls.append({"kind": "link", "kwargs": kwargs})
        return {"url": "https://stripe.test/onboarding"}

    monkeypatch.setattr(
        stripe_api.stripe.AccountLink,
        "create",
        staticmethod(fake_account_link_create),
    )

    url = stripe_api.create_connect_onboarding_link(user)
    assert url.startswith("https://stripe.test")

    link_calls = [c for c in calls if c["kind"] == "link"]
    assert link_calls, "Should create onboarding link"
