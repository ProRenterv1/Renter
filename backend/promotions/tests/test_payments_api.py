from decimal import ROUND_HALF_UP, Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from payments.models import Transaction
from promotions.models import PromotedSlot


def _expected_base_and_gst(price_per_day_cents: int, days: int) -> tuple[int, int]:
    base = price_per_day_cents * days
    gst = int((Decimal(base) * Decimal("0.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return base, gst


@pytest.mark.django_db
def test_promotions_endpoints_require_authentication(listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1500
    client = APIClient()

    pricing_resp = client.get(
        reverse("promotions:promotion_pricing") + f"?listing_id={listing.id}",
        format="json",
    )
    assert pricing_resp.status_code == 401

    base_cents, gst_cents = _expected_base_and_gst(settings.PROMOTION_PRICE_CENTS, 3)
    pay_resp = client.post(
        reverse("promotions:promotion_pay"),
        {
            "listing_id": listing.id,
            "promotion_start": "2025-02-01",
            "promotion_end": "2025-02-03",
            "base_price_cents": base_cents,
            "gst_cents": gst_cents,
            "stripe_payment_method_id": "pm_unauth",
        },
        format="json",
    )
    assert pay_resp.status_code == 401


@pytest.mark.django_db
def test_pay_for_promotion_creates_slot(monkeypatch, owner_user, listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1500
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda user, customer_id=None: "cus_test_123",
    )

    charge_calls = {}

    def _charge(**kwargs):
        charge_calls.update(kwargs)
        return "pi_test_123"

    monkeypatch.setattr("promotions.api.charge_promotion_payment", _charge)

    duration_days = 7
    base_price_cents, gst_cents = _expected_base_and_gst(
        settings.PROMOTION_PRICE_CENTS, duration_days
    )
    payload = {
        "listing_id": listing.id,
        "promotion_start": "2025-01-10",
        "promotion_end": "2025-01-16",
        "base_price_cents": base_price_cents,
        "gst_cents": gst_cents,
        "stripe_payment_method_id": "pm_test_123",
        "stripe_customer_id": "",
    }

    response = api_client.post(reverse("promotions:promotion_pay"), payload, format="json")
    assert response.status_code == 201
    data = response.json()
    assert "slot" in data
    slot_data = data["slot"]
    slot = PromotedSlot.objects.get(pk=slot_data["id"])
    assert slot.listing_id == listing.id
    assert slot.owner_id == owner_user.id
    assert slot.active is True
    assert slot.price_per_day_cents == settings.PROMOTION_PRICE_CENTS
    assert slot.base_price_cents == base_price_cents
    assert slot.gst_cents == gst_cents
    assert slot.total_price_cents > slot.price_per_day_cents
    assert slot.stripe_session_id == "pi_test_123"
    assert charge_calls["amount_cents"] == slot.total_price_cents
    txn = Transaction.objects.get(kind=Transaction.Kind.PROMOTION_CHARGE)
    assert txn.promotion_slot_id == slot.id
    assert txn.booking is None
    assert txn.amount == Decimal(slot.total_price_cents) / Decimal("100")


@pytest.mark.django_db
def test_pay_for_promotion_requires_owner(monkeypatch, owner_user, other_user, listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1500
    api_client = APIClient()
    api_client.force_authenticate(other_user)

    base_cents, gst_cents = _expected_base_and_gst(settings.PROMOTION_PRICE_CENTS, 7)
    payload = {
        "listing_id": listing.id,
        "promotion_start": "2025-01-10",
        "promotion_end": "2025-01-16",
        "base_price_cents": base_cents,
        "gst_cents": gst_cents,
        "stripe_payment_method_id": "pm_test_123",
    }

    response = api_client.post(reverse("promotions:promotion_pay"), payload, format="json")
    assert response.status_code == 403
    assert PromotedSlot.objects.count() == 0


@pytest.mark.django_db
def test_pay_for_promotion_rejects_mismatched_totals(monkeypatch, owner_user, listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1500
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda user, customer_id=None: "cus_test_123",
    )
    monkeypatch.setattr("promotions.api.charge_promotion_payment", lambda **kwargs: "pi_test_123")

    payload = {
        "listing_id": listing.id,
        "promotion_start": "2025-01-10",
        "promotion_end": "2025-01-16",
        "base_price_cents": 100,  # incorrect on purpose
        "gst_cents": 5,
        "stripe_payment_method_id": "pm_test_123",
    }

    response = api_client.post(reverse("promotions:promotion_pay"), payload, format="json")

    assert response.status_code == 400
    data = response.json()
    assert "base_price_cents" in data
    assert "gst_cents" in data
