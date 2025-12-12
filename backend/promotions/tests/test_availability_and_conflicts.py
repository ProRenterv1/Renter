from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from promotions.api import PROMOTION_CONFLICT_MESSAGE
from promotions.models import PromotedSlot


def _combine(value: date) -> datetime:
    current_tz = timezone.get_current_timezone()
    combined = datetime.combine(value, time.min)
    return timezone.make_aware(combined, current_tz)


def _expected_base_and_gst(price_per_day_cents: int, days: int) -> tuple[int, int]:
    base = price_per_day_cents * days
    gst = int((Decimal(base) * Decimal("0.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return base, gst


@pytest.mark.django_db
def test_pay_for_promotion_rejects_overlap(monkeypatch, owner_user, listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1200
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    existing_start = date(2025, 12, 10)
    existing_ends_at = _combine(existing_start) + timedelta(days=5)
    PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=settings.PROMOTION_PRICE_CENTS,
        base_price_cents=0,
        gst_cents=0,
        total_price_cents=0,
        starts_at=_combine(existing_start),
        ends_at=existing_ends_at,
        active=True,
    )

    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda user, customer_id=None: "cus_test_conflict",
    )
    monkeypatch.setattr(
        "promotions.api.charge_promotion_payment", lambda **kwargs: "pi_test_conflict"
    )

    overlap_start = date(2025, 12, 12)
    overlap_end = date(2025, 12, 16)
    duration_days = (overlap_end - overlap_start).days + 1
    base_cents, gst_cents = _expected_base_and_gst(settings.PROMOTION_PRICE_CENTS, duration_days)

    response = api_client.post(
        reverse("promotions:promotion_pay"),
        {
            "listing_id": listing.id,
            "promotion_start": overlap_start.isoformat(),
            "promotion_end": overlap_end.isoformat(),
            "base_price_cents": base_cents,
            "gst_cents": gst_cents,
            "stripe_payment_method_id": "pm_test_conflict",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.data["detail"] == PROMOTION_CONFLICT_MESSAGE
    assert PromotedSlot.objects.count() == 1


@pytest.mark.django_db
def test_pay_for_promotion_allows_adjacent_slot(monkeypatch, owner_user, listing, settings):
    settings.PROMOTION_PRICE_CENTS = 1500
    api_client = APIClient()
    api_client.force_authenticate(owner_user)

    first_start = date(2025, 12, 10)
    first_starts_at = _combine(first_start)
    first_duration_days = 5
    PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=settings.PROMOTION_PRICE_CENTS,
        base_price_cents=0,
        gst_cents=0,
        total_price_cents=0,
        starts_at=first_starts_at,
        ends_at=first_starts_at + timedelta(days=first_duration_days),
        active=True,
    )

    monkeypatch.setattr(
        "promotions.api.ensure_stripe_customer",
        lambda user, customer_id=None: "cus_test_adjacent",
    )
    monkeypatch.setattr(
        "promotions.api.charge_promotion_payment", lambda **kwargs: "pi_test_adjacent"
    )

    next_start = first_start + timedelta(days=first_duration_days)
    next_end = next_start + timedelta(days=2)
    duration_days = (next_end - next_start).days + 1
    base_cents, gst_cents = _expected_base_and_gst(settings.PROMOTION_PRICE_CENTS, duration_days)

    response = api_client.post(
        reverse("promotions:promotion_pay"),
        {
            "listing_id": listing.id,
            "promotion_start": next_start.isoformat(),
            "promotion_end": next_end.isoformat(),
            "base_price_cents": base_cents,
            "gst_cents": gst_cents,
            "stripe_payment_method_id": "pm_test_adjacent",
        },
        format="json",
    )

    assert response.status_code == 201, response.content
    assert PromotedSlot.objects.count() == 2
    new_slot = PromotedSlot.objects.latest("id")
    assert timezone.localtime(new_slot.starts_at).date() == next_start
    assert timezone.localtime(new_slot.ends_at).date() == (next_end + timedelta(days=1))


@pytest.mark.django_db
def test_promotion_availability_returns_inclusive_ranges(owner_user, listing, api_client):
    api_client.force_authenticate(owner_user)
    start_date = date.today() + timedelta(days=3)
    starts_at = _combine(start_date)
    PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=1000,
        base_price_cents=0,
        gst_cents=0,
        total_price_cents=0,
        starts_at=starts_at,
        ends_at=starts_at + timedelta(days=4),
        active=True,
    )
    # Expired slot should be ignored
    past_start = date.today() - timedelta(days=10)
    past_start_dt = _combine(past_start)
    PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=1000,
        base_price_cents=0,
        gst_cents=0,
        total_price_cents=0,
        starts_at=past_start_dt,
        ends_at=timezone.now() - timedelta(days=1),
        active=True,
    )

    response = api_client.get(
        reverse("promotions:promotion_availability") + f"?listing_id={listing.id}"
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "start_date": start_date.isoformat(),
            "end_date": (start_date + timedelta(days=3)).isoformat(),
        }
    ]


@pytest.mark.django_db
def test_promotion_availability_requires_owner(other_user, listing, api_client):
    api_client.force_authenticate(other_user)

    response = api_client.get(
        reverse("promotions:promotion_availability") + f"?listing_id={listing.id}"
    )

    assert response.status_code == 403
