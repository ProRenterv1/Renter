from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from bookings.models import Booking
from listings.models import Listing
from listings.services import compute_booking_totals
from payments.ledger import log_transaction
from payments.models import OwnerPayoutAccount, Transaction
from payments.tax import compute_fee_with_gst
from promotions.models import PromotedSlot

User = get_user_model()


@pytest.fixture
def owner_user(db):
    return User.objects.create_user(username="owner", email="owner@example.com", password="pass123")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="other", email="other@example.com", password="pass123")


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Promo Listing",
        description="Promo description",
        daily_price_cad=Decimal("80.00"),
        replacement_value_cad=Decimal("400.00"),
        damage_deposit_cad=Decimal("25.00"),
        city="Edmonton",
        postal_code="T5A 0A1",
        is_active=True,
        is_available=True,
    )


@pytest.fixture
def seeded_earnings(settings, owner_user, listing):
    settings.BOOKING_RENTER_FEE_RATE = Decimal("0.10")
    settings.BOOKING_OWNER_FEE_RATE = Decimal("0.05")
    settings.PROMOTION_PRICE_CENTS = 1000

    start = date.today()
    end = start + timedelta(days=1)
    totals = compute_booking_totals(listing=listing, start_date=start, end_date=end)
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=owner_user,
        start_date=start,
        end_date=end,
        status=Booking.Status.PAID,
        totals=totals,
    )
    log_transaction(
        user=owner_user,
        booking=booking,
        promotion_slot=None,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("50.00"),
        currency="cad",
        stripe_id="seed_txn",
    )
    return Decimal("50.00")


def _promotion_payload(
    listing_id: int,
    start: date,
    end: date,
    price_per_day_cents: int | None = None,
) -> dict:
    if price_per_day_cents is None:
        from django.conf import settings

        price_per_day_cents = int(getattr(settings, "PROMOTION_PRICE_CENTS", 0))
    duration_days = (end - start).days + 1
    base_cents = price_per_day_cents * duration_days
    _, gst_amount, _ = compute_fee_with_gst(Decimal(base_cents) / Decimal("100"))
    gst_cents = int((gst_amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "listing_id": listing_id,
        "promotion_start": start.isoformat(),
        "promotion_end": end.isoformat(),
        "base_price_cents": base_cents,
        "gst_cents": gst_cents,
        "pay_with_earnings": True,
    }


@pytest.mark.django_db
def test_pay_with_earnings_success(monkeypatch, seeded_earnings, owner_user, listing, settings):
    price_per_day_cents = settings.PROMOTION_PRICE_CENTS
    url = reverse("promotions:promotion_pay")
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    today = date.today()
    payload = _promotion_payload(listing.id, today, today + timedelta(days=2), price_per_day_cents)

    monkeypatch.setattr(
        "promotions.api.compute_owner_available_balance",
        lambda user: Decimal("50.00"),
    )
    monkeypatch.setattr(
        "promotions.api.charge_promotion_payment",
        lambda **kwargs: pytest.fail("Should not call Stripe when paying with earnings"),
    )
    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda *args, **kwargs: pytest.fail("Should not create stripe customer for earnings path"),
    )
    monkeypatch.setattr(
        "promotions.api.transfer_earnings_to_platform",
        lambda **kwargs: "tr_promo_success",
    )
    payout_account, _ = OwnerPayoutAccount.objects.get_or_create(
        user=owner_user,
        defaults={
            "stripe_account_id": "acct_earnings_success",
            "payouts_enabled": True,
            "charges_enabled": True,
        },
    )
    payout_account.stripe_account_id = payout_account.stripe_account_id or "acct_earnings_success"
    payout_account.payouts_enabled = True
    payout_account.charges_enabled = True
    payout_account.save(update_fields=["stripe_account_id", "payouts_enabled", "charges_enabled"])
    monkeypatch.setattr("promotions.api.ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr(
        "promotions.api.get_connect_available_balance",
        lambda _acct: Decimal("50.00"),
    )

    response = api_client.post(url, data=payload, format="json")
    assert response.status_code == 201, response.content
    slot_id = response.data["slot"]["id"]
    slot = PromotedSlot.objects.get(pk=slot_id)
    assert slot.owner == owner_user
    assert slot.listing == listing
    assert response.data["slot"]["duration_days"] == 3
    assert (slot.ends_at - slot.starts_at).days == 3
    assert slot.total_price_cents == 3150

    promo_txn = Transaction.objects.get(
        user=owner_user,
        promotion_slot=slot,
        kind=Transaction.Kind.PROMOTION_CHARGE,
    )
    assert Decimal(promo_txn.amount) == Decimal("31.50")
    assert (
        Transaction.objects.filter(
            user=owner_user,
            promotion_slot=slot,
            kind=Transaction.Kind.OWNER_EARNING,
        ).count()
        == 0
    )


@pytest.mark.django_db
def test_pay_with_earnings_insufficient_balance(monkeypatch, seeded_earnings, owner_user, listing):
    url = reverse("promotions:promotion_pay")
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    today = date.today()
    payload = _promotion_payload(listing.id, today, today + timedelta(days=2))

    monkeypatch.setattr(
        "promotions.api.compute_owner_available_balance",
        lambda user: Decimal("10.00"),
    )
    monkeypatch.setattr(
        "promotions.api.transfer_earnings_to_platform",
        lambda **kwargs: pytest.fail("should not transfer with insufficient balance"),
    )
    payout_account, _ = OwnerPayoutAccount.objects.get_or_create(
        user=owner_user,
        defaults={
            "stripe_account_id": "acct_earnings_low",
            "payouts_enabled": True,
            "charges_enabled": True,
        },
    )
    payout_account.stripe_account_id = payout_account.stripe_account_id or "acct_earnings_low"
    payout_account.payouts_enabled = True
    payout_account.charges_enabled = True
    payout_account.save(update_fields=["stripe_account_id", "payouts_enabled", "charges_enabled"])
    monkeypatch.setattr("promotions.api.ensure_connect_account", lambda user: payout_account)
    monkeypatch.setattr(
        "promotions.api.get_connect_available_balance",
        lambda _acct: Decimal("10.00"),
    )
    response = api_client.post(url, data=payload, format="json")

    assert response.status_code == 400
    assert "Not enough earnings" in response.data["detail"]
    assert PromotedSlot.objects.count() == 0
    assert Transaction.objects.filter(kind=Transaction.Kind.PROMOTION_CHARGE).count() == 0
    # Only the seeded earning should exist
    owner_earnings = Transaction.objects.filter(
        user=owner_user, kind=Transaction.Kind.OWNER_EARNING
    )
    assert owner_earnings.count() == 1


@pytest.mark.django_db
def test_non_owner_cannot_pay_with_earnings(monkeypatch, seeded_earnings, other_user, listing):
    url = reverse("promotions:promotion_pay")
    api_client = APIClient()
    api_client.force_authenticate(other_user)

    today = date.today()
    payload = _promotion_payload(listing.id, today, today + timedelta(days=2))

    response = api_client.post(url, data=payload, format="json")

    assert response.status_code == 403
    assert PromotedSlot.objects.count() == 0
    assert Transaction.objects.filter(kind=Transaction.Kind.PROMOTION_CHARGE).count() == 0
    assert (
        Transaction.objects.filter(
            user=listing.owner,
            kind=Transaction.Kind.OWNER_EARNING,
        ).count()
        == 1
    )
