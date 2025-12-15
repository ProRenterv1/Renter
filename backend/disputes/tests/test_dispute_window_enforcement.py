from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Booking
from disputes.models import DisputeCase
from operator_bookings.models import BookingEvent

pytestmark = pytest.mark.django_db


def auth(user):
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = token_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_return_confirmation_sets_dispute_window(booking_factory, renter_user):
    booking = booking_factory(
        start_date=timezone.localdate() - timedelta(days=3),
        end_date=timezone.localdate() - timedelta(days=1),
        status=Booking.Status.PAID,
        renter=renter_user,
        returned_by_renter_at=timezone.now(),
    )
    client = auth(booking.owner)
    resp = client.post(f"/api/bookings/{booking.id}/owner-mark-returned/", {}, format="json")

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.return_confirmed_at is not None
    assert booking.dispute_window_expires_at is not None
    delta = booking.dispute_window_expires_at - booking.return_confirmed_at
    assert timedelta(hours=23) < delta < timedelta(hours=25)


def test_complete_blocked_without_return_confirmation(booking_factory, renter_user):
    booking = booking_factory(
        start_date=timezone.localdate() - timedelta(days=3),
        end_date=timezone.localdate() - timedelta(days=1),
        status=Booking.Status.PAID,
        renter=renter_user,
        return_confirmed_at=None,
    )
    client = auth(booking.owner)
    resp = client.post(f"/api/bookings/{booking.id}/complete/", {}, format="json")

    assert resp.status_code == 400
    assert "return_confirmed_at" in resp.data


def test_dispute_after_expiry_allows_safety_and_records_event(booking_factory, renter_user):
    now = timezone.now()
    booking = booking_factory(
        start_date=timezone.localdate() - timedelta(days=5),
        end_date=timezone.localdate() - timedelta(days=3),
        status=Booking.Status.COMPLETED,
        renter=renter_user,
        dispute_window_expires_at=now - timedelta(hours=1),
        deposit_hold_id="pi_test",
    )
    client = auth(renter_user)
    resp = client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.SAFETY_OR_FRAUD,
            "damage_flow_kind": DisputeCase.DamageFlowKind.GENERIC,
            "description": "safety issue",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    booking.refresh_from_db()
    dispute = DisputeCase.objects.get(id=resp.data["id"])
    assert dispute.status == DisputeCase.Status.OPEN
    assert booking.deposit_locked is True
    assert booking.is_disputed is True
    event = BookingEvent.objects.filter(booking=booking, payload__dispute_id=dispute.id).first()
    assert event is not None
    assert event.payload.get("auto_closed") is False


def test_dispute_after_expiry_auto_closes_and_no_deposit_lock(booking_factory, renter_user):
    now = timezone.now()
    booking = booking_factory(
        start_date=timezone.localdate() - timedelta(days=5),
        end_date=timezone.localdate() - timedelta(days=3),
        status=Booking.Status.COMPLETED,
        renter=renter_user,
        dispute_window_expires_at=now - timedelta(hours=2),
        deposit_hold_id="pi_test",
    )
    client = auth(renter_user)
    resp = client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "damage_flow_kind": DisputeCase.DamageFlowKind.GENERIC,
            "description": "too late",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data
    booking.refresh_from_db()
    dispute = DisputeCase.objects.get(id=resp.data["id"])
    assert dispute.status == DisputeCase.Status.CLOSED_AUTO
    assert dispute.resolved_at is not None
    assert dispute.deposit_locked is False
    assert booking.deposit_locked is False
    assert booking.is_disputed is False
    event = BookingEvent.objects.filter(booking=booking, payload__dispute_id=dispute.id).first()
    assert event is not None
    assert event.payload.get("auto_closed") is True
