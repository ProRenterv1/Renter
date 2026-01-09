from __future__ import annotations

import pytest
import stripe
from rest_framework.test import APIClient

from payments import payment_methods_api
from payments.models import PaymentMethod

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


def test_payment_methods_list_is_scoped_to_user(renter_user, other_user):
    user_pm = PaymentMethod.objects.create(
        user=renter_user,
        stripe_payment_method_id="pm_user",
        brand="VISA",
        last4="4242",
        is_default=True,
    )
    PaymentMethod.objects.create(
        user=other_user,
        stripe_payment_method_id="pm_other",
        brand="MC",
        last4="9999",
    )

    client = _auth_client(renter_user)
    resp = client.get("/api/payments/methods/")

    assert resp.status_code == 200
    assert len(resp.data) == 1
    result = resp.data[0]
    assert result["id"] == user_pm.id
    assert result["stripe_payment_method_id"] == "pm_user"
    assert result["last4"] == "4242"
    assert result["is_default"] is True


def test_create_payment_method_attaches_and_sets_default(monkeypatch, renter_user, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"

    customer_calls = {"count": 0}
    attach_calls = {"called": False, "customer_id": None, "payment_method_id": None}

    def _fake_customer(user):
        customer_calls["count"] += 1
        return "cus_123"

    monkeypatch.setattr(payment_methods_api, "ensure_stripe_customer", _fake_customer)

    def _fake_attach(payment_method_id: str, customer_id: str):
        attach_calls["called"] = True
        attach_calls["customer_id"] = customer_id
        attach_calls["payment_method_id"] = payment_method_id

    monkeypatch.setattr(payment_methods_api, "_ensure_payment_method_for_customer", _fake_attach)
    monkeypatch.setattr(
        payment_methods_api,
        "fetch_payment_method_details",
        lambda payment_method_id: {
            "brand": "visa",
            "last4": "1111",
            "exp_month": 12,
            "exp_year": 2030,
        },
    )

    client = _auth_client(renter_user)
    resp = client.post(
        "/api/payments/methods/",
        {"stripe_payment_method_id": "pm_new"},
        format="json",
    )

    assert resp.status_code == 201, resp.data
    assert customer_calls["count"] == 1
    assert attach_calls["called"] is True
    assert attach_calls["customer_id"] == "cus_123"
    assert attach_calls["payment_method_id"] == "pm_new"

    pm = PaymentMethod.objects.get(user=renter_user)
    assert pm.is_default is True
    assert pm.brand == "VISA"
    assert pm.last4 == "1111"
    assert pm.exp_month == 12
    assert pm.exp_year == 2030
    assert resp.data["brand"] == "VISA"
    assert resp.data["stripe_payment_method_id"] == "pm_new"


def test_set_default_updates_flags(renter_user):
    pm1 = PaymentMethod.objects.create(
        user=renter_user,
        stripe_payment_method_id="pm_one",
        brand="VISA",
        last4="1111",
        is_default=True,
    )
    pm2 = PaymentMethod.objects.create(
        user=renter_user,
        stripe_payment_method_id="pm_two",
        brand="MC",
        last4="2222",
        is_default=False,
    )

    client = _auth_client(renter_user)
    resp = client.post(f"/api/payments/methods/{pm2.id}/set-default/")

    assert resp.status_code == 200
    pm1.refresh_from_db()
    pm2.refresh_from_db()
    assert pm1.is_default is False
    assert pm2.is_default is True
    assert resp.data["id"] == pm2.id
    assert resp.data["is_default"] is True
    assert resp.data["stripe_payment_method_id"] == pm2.stripe_payment_method_id
    assert PaymentMethod.objects.filter(user=renter_user, is_default=True).count() == 1


def test_delete_payment_method_detaches_best_effort(monkeypatch, renter_user, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"

    pm = PaymentMethod.objects.create(
        user=renter_user,
        stripe_payment_method_id="pm_delete",
        brand="VISA",
        last4="3333",
        is_default=True,
    )

    detach_calls = {"count": 0, "last_id": None}

    class DummyStripeError(stripe.error.StripeError):
        def __init__(self, msg="boom", *args):
            super().__init__(msg, *args)

    class DummyPaymentMethod:
        @staticmethod
        def detach(payment_method_id: str):
            detach_calls["count"] += 1
            detach_calls["last_id"] = payment_method_id
            raise DummyStripeError("fail")

    monkeypatch.setattr(payment_methods_api.stripe, "PaymentMethod", DummyPaymentMethod)

    client = _auth_client(renter_user)
    resp = client.delete(f"/api/payments/methods/{pm.id}/")

    assert resp.status_code == 204
    assert PaymentMethod.objects.filter(id=pm.id).count() == 0
    assert detach_calls["count"] == 1
    assert detach_calls["last_id"] == "pm_delete"


def test_setup_intent_endpoint_uses_reuse_helper(monkeypatch, renter_user, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"

    class DummySetupIntent:
        def __init__(self):
            self.stripe_setup_intent_id = "seti_test_123"
            self.client_secret = "seti_test_123_secret"
            self.status = "open"
            self.intent_type = "default_card"

    helper_calls = {"count": 0, "intent_type": None}

    def _fake_reuse(user, intent_type, cache_scope=None):
        helper_calls["count"] += 1
        helper_calls["intent_type"] = intent_type
        return DummySetupIntent()

    monkeypatch.setattr(payment_methods_api, "create_or_reuse_setup_intent", _fake_reuse)

    client = _auth_client(renter_user)
    resp = client.post(
        "/api/payments/methods/setup-intent/",
        {"intent_type": "default_card"},
        format="json",
    )

    assert resp.status_code == 200
    assert helper_calls["count"] == 1
    assert helper_calls["intent_type"] == "default_card"
    assert resp.data["setup_intent_id"] == "seti_test_123"
    assert resp.data["client_secret"] == "seti_test_123_secret"
