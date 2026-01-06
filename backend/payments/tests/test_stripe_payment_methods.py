from types import SimpleNamespace

import pytest

from payments import stripe_api


@pytest.mark.django_db
def test_ensure_payment_method_detaches_before_attach(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test"

    class DummyPaymentMethodAPI:
        def __init__(self):
            self.retrieve_calls = []
            self.detach_calls = []
            self.attach_calls = []

        def retrieve(self, payment_method_id):
            self.retrieve_calls.append(payment_method_id)
            return SimpleNamespace(customer="cus_other")

        def detach(self, payment_method_id):
            self.detach_calls.append(payment_method_id)
            return SimpleNamespace(id=payment_method_id)

        def attach(self, payment_method_id, customer=None):
            self.attach_calls.append((payment_method_id, customer))
            return SimpleNamespace(id=payment_method_id, customer=customer)

    dummy_api = DummyPaymentMethodAPI()
    monkeypatch.setattr(stripe_api.stripe, "PaymentMethod", dummy_api)

    stripe_api._ensure_payment_method_for_customer("pm_saved", "cus_target")

    assert dummy_api.retrieve_calls == ["pm_saved"]
    assert dummy_api.detach_calls == ["pm_saved"]
    assert dummy_api.attach_calls == [("pm_saved", "cus_target")]
