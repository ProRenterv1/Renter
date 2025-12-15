import importlib
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework.test import APIClient

import renter.urls as renter_urls
from bookings.models import Booking
from disputes.models import DisputeCase
from operator_bookings.models import BookingEvent

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def enable_operator_routes(settings):
    original_enable = settings.ENABLE_OPERATOR
    original_hosts = getattr(settings, "OPS_ALLOWED_HOSTS", [])
    original_allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))

    settings.ENABLE_OPERATOR = True
    settings.OPS_ALLOWED_HOSTS = ["ops.example.com"]
    settings.ALLOWED_HOSTS = ["ops.example.com", "public.example.com", "testserver"]
    clear_url_caches()
    importlib.reload(renter_urls)
    yield
    settings.ENABLE_OPERATOR = original_enable
    settings.OPS_ALLOWED_HOSTS = original_hosts
    settings.ALLOWED_HOSTS = original_allowed_hosts
    clear_url_caches()
    importlib.reload(renter_urls)


@pytest.fixture
def operator_user():
    group, _ = Group.objects.get_or_create(name="operator_support")
    user = User.objects.create_user(
        username="operator",
        email="operator@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


def _ops_client(user=None):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    if user:
        client.force_authenticate(user=user)
    return client


def _results(resp):
    return (
        resp.data["results"]
        if isinstance(resp.data, dict) and "results" in resp.data
        else resp.data
    )


def test_operator_bookings_requires_operator(listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    client = _ops_client()
    resp = client.get("/api/operator/bookings/")
    assert resp.status_code in (401, 403)
    assert booking is not None


def test_operator_bookings_filters(operator_user, listing, owner_user, renter_user, other_user):
    now = timezone.now()
    old = now - timedelta(days=2)
    booking_recent = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.PAID,
        return_confirmed_at=None,
    )
    Booking.objects.filter(pk=booking_recent.id).update(created_at=now)
    booking_old = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=other_user,
        start_date=timezone.localdate() - timedelta(days=3),
        end_date=timezone.localdate() - timedelta(days=1),
        status=Booking.Status.CONFIRMED,
    )
    Booking.objects.filter(pk=booking_old.id).update(created_at=old)

    overdue_booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate() - timedelta(days=5),
        end_date=timezone.localdate() - timedelta(days=2),
        status=Booking.Status.PAID,
        return_confirmed_at=None,
    )

    client = _ops_client(operator_user)
    resp = client.get(
        "/api/operator/bookings/",
        {
            "status": "paid",
            "owner": owner_user.id,
            "renter": renter_user.id,
            "created_at_after": (now - timedelta(hours=1)).isoformat(),
            "created_at_before": (now + timedelta(hours=1)).isoformat(),
        },
    )
    assert resp.status_code == 200, resp.data
    payload = _results(resp)
    assert len(payload) == 1
    assert payload[0]["id"] == booking_recent.id

    resp_overdue = client.get("/api/operator/bookings/", {"overdue": True})
    payload_overdue = _results(resp_overdue)
    assert resp_overdue.status_code == 200
    assert overdue_booking.id in [b["id"] for b in payload_overdue]
    assert booking_recent.id not in [b["id"] for b in payload_overdue]


def test_operator_booking_detail_includes_events_and_disputes(
    operator_user, listing, owner_user, renter_user
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=timezone.localdate(),
        end_date=timezone.localdate() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    earlier = timezone.now() - timedelta(hours=1)
    event1 = BookingEvent.objects.create(
        booking=booking,
        type=BookingEvent.Type.STATUS_CHANGE,
        payload={"from": "paid", "to": "completed"},
    )
    BookingEvent.objects.filter(pk=event1.id).update(created_at=earlier)
    event2 = BookingEvent.objects.create(
        booking=booking, type=BookingEvent.Type.OPERATOR_ACTION, payload={"note": "checked"}
    )
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="desc",
        status=DisputeCase.Status.OPEN,
    )

    client = _ops_client(operator_user)
    resp = client.get(f"/api/operator/bookings/{booking.id}/")

    assert resp.status_code == 200, resp.data
    events = resp.data["events"]
    assert [e["id"] for e in events] == [event1.id, event2.id]
    disputes = resp.data["disputes"]
    assert disputes[0]["id"] == dispute.id
    assert disputes[0]["status"] == dispute.status
