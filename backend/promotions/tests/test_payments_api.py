from decimal import ROUND_HALF_UP, Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from payments.ledger import log_transaction
from payments.models import OwnerPayoutAccount, Transaction
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
    assert charge_calls["payment_method_id"] == "pm_test_123"
    assert charge_calls["customer_id"] == "cus_test_123"
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


@pytest.mark.django_db
def test_pay_for_promotion_with_earnings(monkeypatch, owner_user, listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1500
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda *args, **kwargs: pytest.fail("should not hit stripe customer"),
    )
    monkeypatch.setattr(
        "promotions.api.charge_promotion_payment",
        lambda **kwargs: pytest.fail("should not charge stripe"),
    )
    monkeypatch.setattr(
        "promotions.api.transfer_earnings_to_platform",
        lambda **kwargs: "tr_test_promo",
    )
    payout_account, _ = OwnerPayoutAccount.objects.get_or_create(
        user=owner_user,
        defaults={
            "stripe_account_id": "acct_test_earnings",
            "payouts_enabled": True,
            "charges_enabled": True,
        },
    )
    payout_account.stripe_account_id = payout_account.stripe_account_id or "acct_test_earnings"
    payout_account.payouts_enabled = True
    payout_account.charges_enabled = True
    payout_account.save(update_fields=["stripe_account_id", "payouts_enabled", "charges_enabled"])
    monkeypatch.setattr("promotions.api.ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr(
        "promotions.api.get_connect_available_balance",
        lambda _acct: Decimal("1000.00"),
    )

    log_transaction(
        user=owner_user,
        booking=None,
        promotion_slot=None,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("500.00"),
    )

    duration_days = 3
    base_cents, gst_cents = _expected_base_and_gst(settings.PROMOTION_PRICE_CENTS, duration_days)
    payload = {
        "listing_id": listing.id,
        "promotion_start": "2025-03-01",
        "promotion_end": "2025-03-03",
        "base_price_cents": base_cents,
        "gst_cents": gst_cents,
        "pay_with_earnings": True,
    }

    response = api_client.post(reverse("promotions:promotion_pay"), payload, format="json")

    assert response.status_code == 201, response.json()
    slot = PromotedSlot.objects.get(pk=response.data["slot"]["id"])
    assert slot.stripe_session_id == ""
    total_amount = (Decimal(base_cents + gst_cents) / Decimal("100")).quantize(Decimal("0.01"))

    txn_promo = Transaction.objects.filter(
        promotion_slot_id=slot.id, kind=Transaction.Kind.PROMOTION_CHARGE
    )
    assert txn_promo.filter(amount=total_amount).exists()
    assert txn_promo.filter(stripe_id="tr_test_promo").exists()
    assert (
        Transaction.objects.filter(
            promotion_slot_id=slot.id, kind=Transaction.Kind.OWNER_EARNING
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_pay_for_promotion_with_earnings_insufficient_balance(
    monkeypatch, owner_user, listing, settings
):
    settings.PROMOTION_PRICE_CENTS = 1500
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda *args, **kwargs: pytest.fail("should not hit stripe customer"),
    )
    monkeypatch.setattr(
        "promotions.api.charge_promotion_payment",
        lambda **kwargs: pytest.fail("should not charge stripe"),
    )
    monkeypatch.setattr(
        "promotions.api.transfer_earnings_to_platform",
        lambda **kwargs: pytest.fail("should not transfer when insufficient"),
    )
    payout_account, _ = OwnerPayoutAccount.objects.get_or_create(
        user=owner_user,
        defaults={
            "stripe_account_id": "acct_test_earnings_low",
            "payouts_enabled": True,
            "charges_enabled": True,
        },
    )
    payout_account.stripe_account_id = payout_account.stripe_account_id or "acct_test_earnings_low"
    payout_account.payouts_enabled = True
    payout_account.charges_enabled = True
    payout_account.save(update_fields=["stripe_account_id", "payouts_enabled", "charges_enabled"])
    monkeypatch.setattr("promotions.api.ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr(
        "promotions.api.get_connect_available_balance",
        lambda _acct: Decimal("10.00"),
    )

    log_transaction(
        user=owner_user,
        booking=None,
        promotion_slot=None,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("10.00"),
    )

    duration_days = 7
    base_cents, gst_cents = _expected_base_and_gst(settings.PROMOTION_PRICE_CENTS, duration_days)
    payload = {
        "listing_id": listing.id,
        "promotion_start": "2025-03-01",
        "promotion_end": "2025-03-07",
        "base_price_cents": base_cents,
        "gst_cents": gst_cents,
        "pay_with_earnings": True,
    }

    response = api_client.post(reverse("promotions:promotion_pay"), payload, format="json")

    assert response.status_code == 400
    assert response.data["detail"] == "Not enough earnings to pay for this promotion."
    assert response.data["available_earnings"] == "10.00"
    assert PromotedSlot.objects.count() == 0
