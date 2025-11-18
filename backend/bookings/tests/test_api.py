"""Integration tests for the bookings API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from bookings.models import Booking
from listings.models import Listing
from notifications import tasks as notification_tasks

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


def booking_payload(listing, start, end):
    return {
        "listing": listing.id,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
    }


def test_create_booking_success(renter_user, listing):
    client = auth(renter_user)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=3)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == Booking.Status.REQUESTED
    assert resp.data["owner"] == listing.owner_id
    assert resp.data["renter"] == renter_user.id
    assert {"days", "total_charge"} <= set(resp.data["totals"].keys())


def test_create_booking_queues_owner_notification(renter_user, listing, monkeypatch):
    client = auth(renter_user)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=4)

    captured = []

    def _capture(owner_id, booking_id):
        captured.append((owner_id, booking_id))

    monkeypatch.setattr(notification_tasks.send_booking_request_email, "delay", _capture)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 201
    assert captured
    assert captured[0][0] == listing.owner_id
    assert captured[0][1] == resp.data["id"]


def test_confirm_booking_notifies_renter(booking_factory, owner_user, renter_user, monkeypatch):
    booking = booking_factory(
        start_date=date.today() + timedelta(days=6),
        end_date=date.today() + timedelta(days=8),
        status=Booking.Status.REQUESTED,
    )
    owner_client = auth(owner_user)

    captured = []

    def _capture(renter_id, booking_id, status):
        captured.append((renter_id, booking_id, status))

    monkeypatch.setattr(notification_tasks.send_booking_status_email, "delay", _capture)

    resp = owner_client.post(f"/api/bookings/{booking.id}/confirm/")

    assert resp.status_code == 200
    assert captured
    assert captured[0][0] == booking.renter_id
    assert captured[0][1] == booking.id
    assert captured[0][2] == Booking.Status.CONFIRMED


def test_owner_cancel_booking_notifies_renter(
    booking_factory,
    owner_user,
    renter_user,
    monkeypatch,
):
    booking = booking_factory(
        start_date=date.today() + timedelta(days=7),
        end_date=date.today() + timedelta(days=9),
        status=Booking.Status.REQUESTED,
    )
    owner_client = auth(owner_user)

    captured = []

    def _capture(renter_id, booking_id, status):
        captured.append((renter_id, booking_id, status))

    monkeypatch.setattr(notification_tasks.send_booking_status_email, "delay", _capture)

    resp = owner_client.post(f"/api/bookings/{booking.id}/cancel/")

    assert resp.status_code == 200
    assert captured
    assert captured[0][0] == booking.renter_id
    assert captured[0][1] == booking.id
    assert captured[0][2] == Booking.Status.CANCELED


def test_cannot_book_own_listing(owner_user, listing):
    client = auth(owner_user)
    start = date.today() + timedelta(days=4)
    end = start + timedelta(days=2)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert "own listing" in resp.data["listing"][0].lower()


def test_booking_conflict_rejected(booking_factory, listing, renter_user, other_user):
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=3)
    booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)

    client = auth(other_user)
    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert "not available" in resp.data["non_field_errors"][0]


def test_confirm_booking_owner_only(booking_factory, owner_user, renter_user):
    start = date.today() + timedelta(days=6)
    end = start + timedelta(days=2)
    booking = booking_factory(start_date=start, end_date=end, status=Booking.Status.REQUESTED)

    renter_client = auth(renter_user)
    renter_resp = renter_client.post(f"/api/bookings/{booking.id}/confirm/")
    assert renter_resp.status_code == 403

    owner_client = auth(owner_user)
    owner_resp = owner_client.post(f"/api/bookings/{booking.id}/confirm/")
    assert owner_resp.status_code == 200
    assert owner_resp.data["status"] == Booking.Status.CONFIRMED


def test_cancel_booking_by_owner_or_renter(
    booking_factory,
    owner_user,
    renter_user,
    other_user,
):
    owner_client = auth(owner_user)
    renter_client = auth(renter_user)
    other_client = auth(other_user)

    start = date.today() + timedelta(days=7)
    end = start + timedelta(days=2)
    booking_owner = booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)
    owner_resp = owner_client.post(f"/api/bookings/{booking_owner.id}/cancel/")
    assert owner_resp.status_code == 200
    assert owner_resp.data["status"] == Booking.Status.CANCELED

    booking_renter = booking_factory(
        start_date=end + timedelta(days=1),
        end_date=end + timedelta(days=3),
        status=Booking.Status.CONFIRMED,
    )
    renter_resp = renter_client.post(f"/api/bookings/{booking_renter.id}/cancel/")
    assert renter_resp.status_code == 200
    assert renter_resp.data["status"] == Booking.Status.CANCELED

    booking_forbidden = booking_factory(
        start_date=end + timedelta(days=4),
        end_date=end + timedelta(days=6),
        status=Booking.Status.CONFIRMED,
    )
    forbid_resp = other_client.post(f"/api/bookings/{booking_forbidden.id}/cancel/")
    assert forbid_resp.status_code == 403


def test_complete_booking_owner_only(booking_factory, owner_user, renter_user):
    start = date.today() + timedelta(days=10)
    end = start + timedelta(days=4)
    booking = booking_factory(start_date=start, end_date=end, status=Booking.Status.CONFIRMED)

    renter_client = auth(renter_user)
    renter_resp = renter_client.post(f"/api/bookings/{booking.id}/complete/")
    assert renter_resp.status_code == 403

    owner_client = auth(owner_user)
    owner_resp = owner_client.post(f"/api/bookings/{booking.id}/complete/")
    assert owner_resp.status_code == 200
    assert owner_resp.data["status"] == Booking.Status.COMPLETED


def test_my_bookings_endpoint_lists_owner_and_renter(
    booking_factory,
    owner_user,
    renter_user,
    other_user,
    listing,
):
    second_listing = Listing.objects.create(
        owner=other_user,
        title="Road Bike",
        description="Fast bike",
        daily_price_cad=Decimal("30.00"),
        replacement_value_cad=Decimal("800.00"),
        damage_deposit_cad=Decimal("150.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )

    owner_booking_newer = booking_factory(
        start_date=date.today() + timedelta(days=12),
        end_date=date.today() + timedelta(days=14),
        status=Booking.Status.CONFIRMED,
    )
    owner_booking_older = booking_factory(
        start_date=date.today() + timedelta(days=15),
        end_date=date.today() + timedelta(days=17),
        status=Booking.Status.REQUESTED,
    )
    renter_booking = booking_factory(
        listing_override=second_listing,
        owner=second_listing.owner,
        renter=owner_user,
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=22),
        status=Booking.Status.REQUESTED,
    )
    unrelated_booking = booking_factory(
        listing_override=second_listing,
        owner=second_listing.owner,
        renter=renter_user,
        start_date=date.today() + timedelta(days=25),
        end_date=date.today() + timedelta(days=27),
        status=Booking.Status.CONFIRMED,
    )

    client = auth(owner_user)
    resp = client.get("/api/bookings/my/")
    assert resp.status_code == 200
    returned = {item["id"]: item for item in resp.data}
    assert set(returned.keys()) == {
        owner_booking_newer.id,
        owner_booking_older.id,
        renter_booking.id,
    }
    assert unrelated_booking.id not in returned

    owner_view_data = returned[owner_booking_newer.id]
    assert owner_view_data["renter_first_name"] == renter_user.first_name
    assert owner_view_data["renter_last_name"] == renter_user.last_name
    assert owner_view_data["renter_username"] == renter_user.username
    assert owner_view_data["renter_avatar_url"]

    renter_view_data = returned[renter_booking.id]
    assert renter_view_data["renter_first_name"] == owner_user.first_name
    assert renter_view_data["renter_last_name"] == owner_user.last_name


def test_my_bookings_includes_status_label_for_paid_booking(
    booking_factory,
    renter_user,
):
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=2)
    booking = booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    booking.charge_payment_intent_id = "pi_status_label"
    booking.save(update_fields=["charge_payment_intent_id"])

    client = auth(renter_user)
    resp = client.get("/api/bookings/my/")
    assert resp.status_code == 200
    returned = {item["id"]: item for item in resp.data}
    assert returned[booking.id]["status_label"] == "Waiting pick up"


def test_my_bookings_derives_paid_label_from_charge_id(
    booking_factory,
    renter_user,
):
    start = date.today() + timedelta(days=8)
    end = start + timedelta(days=3)
    booking = booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.REQUESTED,
        renter=renter_user,
    )
    booking.charge_payment_intent_id = "pi_existing_charge"
    booking.save(update_fields=["charge_payment_intent_id"])

    client = auth(renter_user)
    resp = client.get("/api/bookings/my/")
    assert resp.status_code == 200
    returned = {item["id"]: item for item in resp.data}
    assert returned[booking.id]["status_label"] == "Waiting pick up"


def test_pending_requests_count_returns_owner_requested_bookings(
    booking_factory,
    owner_user,
):
    start = date.today() + timedelta(days=5)
    booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    booking_factory(
        start_date=start + timedelta(days=3),
        end_date=start + timedelta(days=5),
        status=Booking.Status.REQUESTED,
    )
    booking_factory(
        start_date=start + timedelta(days=6),
        end_date=start + timedelta(days=7),
        status=Booking.Status.CONFIRMED,
    )

    client = auth(owner_user)
    resp = client.get("/api/bookings/pending-requests-count/")
    assert resp.status_code == 200
    assert resp.data["pending_requests"] == 2


def test_pending_requests_count_excludes_renter_only_bookings(
    owner_user,
    other_user,
):
    start = date.today() + timedelta(days=4)
    other_listing = Listing.objects.create(
        owner=other_user,
        title="Trail Bike",
        description="Great bike",
        daily_price_cad=Decimal("18.00"),
        replacement_value_cad=Decimal("500.00"),
        damage_deposit_cad=Decimal("150.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )
    Booking.objects.create(
        listing=other_listing,
        owner=other_user,
        renter=owner_user,
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    Booking.objects.create(
        listing=other_listing,
        owner=other_user,
        renter=other_user,
        start_date=start + timedelta(days=3),
        end_date=start + timedelta(days=5),
        status=Booking.Status.REQUESTED,
    )

    client = auth(owner_user)
    resp = client.get("/api/bookings/pending-requests-count/")
    assert resp.status_code == 200
    assert resp.data["pending_requests"] == 0


def test_availability_returns_active_bookings_for_listing(
    booking_factory,
    listing,
    other_user,
):
    start = date.today() + timedelta(days=3)
    booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    booking_factory(
        start_date=start + timedelta(days=5),
        end_date=start + timedelta(days=7),
        status=Booking.Status.CONFIRMED,
    )
    booking_factory(
        start_date=start + timedelta(days=9),
        end_date=start + timedelta(days=11),
        status=Booking.Status.PAID,
    )
    other_listing = Listing.objects.create(
        owner=other_user,
        title="Other Listing",
        description="Different listing",
        daily_price_cad=Decimal("10.00"),
        replacement_value_cad=Decimal("500.00"),
        damage_deposit_cad=Decimal("50.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )
    booking_factory(
        listing_override=other_listing,
        start_date=start,
        end_date=start + timedelta(days=1),
        status=Booking.Status.REQUESTED,
    )

    client = APIClient()
    resp = client.get(f"/api/bookings/availability/?listing={listing.id}")
    assert resp.status_code == 200
    assert resp.data == [
        {"start_date": start.isoformat(), "end_date": (start + timedelta(days=2)).isoformat()},
        {
            "start_date": (start + timedelta(days=5)).isoformat(),
            "end_date": (start + timedelta(days=7)).isoformat(),
        },
        {
            "start_date": (start + timedelta(days=9)).isoformat(),
            "end_date": (start + timedelta(days=11)).isoformat(),
        },
    ]


def test_availability_excludes_inactive_bookings(booking_factory, listing):
    start = date.today() + timedelta(days=4)
    booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CANCELED,
    )
    booking_factory(
        start_date=start + timedelta(days=3),
        end_date=start + timedelta(days=5),
        status=Booking.Status.COMPLETED,
    )

    client = APIClient()
    resp = client.get(f"/api/bookings/availability/?listing={listing.id}")
    assert resp.status_code == 200
    assert resp.data == []


def test_availability_requires_listing_query_param():
    client = APIClient()
    resp = client.get("/api/bookings/availability/")
    assert resp.status_code == 400
    assert resp.data["detail"]


def test_availability_returns_404_for_inactive_listing(listing):
    listing.is_active = False
    listing.save(update_fields=["is_active"])
    client = APIClient()
    resp = client.get(f"/api/bookings/availability/?listing={listing.id}")
    assert resp.status_code == 404
