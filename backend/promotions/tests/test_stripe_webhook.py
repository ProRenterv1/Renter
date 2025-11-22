from datetime import timedelta

import pytest
import stripe
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from payments.stripe_api import stripe_webhook
from promotions.models import PromotedSlot


@pytest.mark.django_db
def test_checkout_session_completed_activates_promoted_slot(monkeypatch, owner_user, listing):
    start = timezone.now() + timedelta(days=1)
    duration_days = 7
    slot = PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=1500,
        total_price_cents=1500 * duration_days,
        starts_at=start,
        ends_at=start + timedelta(days=duration_days),
        active=False,
        stripe_session_id="cs_test_123",
    )

    event_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": slot.stripe_session_id,
                "metadata": {
                    "kind": "promotion_slot",
                    "starts_at": slot.starts_at.isoformat(),
                    "ends_at": slot.ends_at.isoformat(),
                },
            }
        },
    }
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda payload, sig_header, secret: event_payload,
    )

    factory = APIRequestFactory()
    request = factory.post("/api/payments/stripe/webhook/", data={}, format="json")

    response = stripe_webhook(request)
    assert response.status_code == 200

    slot.refresh_from_db()
    assert slot.active is True
    assert slot.starts_at == start
    assert slot.ends_at == start + timedelta(days=duration_days)


@pytest.mark.django_db
def test_checkout_session_completed_is_idempotent(monkeypatch, owner_user, listing):
    initial_start = timezone.now()
    duration_days = 3
    slot = PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=2000,
        total_price_cents=2000 * duration_days,
        starts_at=initial_start,
        ends_at=initial_start + timedelta(days=duration_days),
        active=True,
        stripe_session_id="cs_test_abc",
    )

    event_payload = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": slot.stripe_session_id,
                "metadata": {"kind": "promotion_slot"},
            }
        },
    }
    monkeypatch.setattr(
        stripe.Webhook,
        "construct_event",
        lambda payload, sig_header, secret: event_payload,
    )

    later_now = timezone.now() + timedelta(days=10)
    monkeypatch.setattr("payments.stripe_api.timezone.now", lambda: later_now)

    factory = APIRequestFactory()
    request = factory.post("/api/payments/stripe/webhook/", data={}, format="json")

    response = stripe_webhook(request)
    assert response.status_code == 200

    slot.refresh_from_db()
    assert slot.starts_at == initial_start
    assert slot.ends_at == initial_start + timedelta(days=duration_days)
