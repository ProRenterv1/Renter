"""Integration tests for the bookings API endpoints."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings import api as bookings_api
from bookings.models import Booking, BookingPhoto
from listings.models import Listing
from listings.services import compute_booking_totals
from notifications import tasks as notification_tasks
from payments.ledger import log_transaction
from payments.models import Transaction

pytestmark = pytest.mark.django_db

EXPECTED_TOTAL_KEYS = {
    "days",
    "daily_price_cad",
    "rental_subtotal",
    "service_fee",
    "renter_fee",
    "owner_fee",
    "platform_fee_total",
    "owner_payout",
    "damage_deposit",
    "total_charge",
}
CURRENCY_QUANTIZE = Decimal("0.01")


def _format_currency(value: Decimal | str | float | int) -> str:
    return f"${Decimal(value).quantize(CURRENCY_QUANTIZE)}"


def booking_limit_error_message(settings) -> str:
    return (
        "This booking is only available to users with ID verification. "
        "Unverified profiles are limited to tools up to "
        f"{_format_currency(settings.UNVERIFIED_MAX_REPLACEMENT_CAD)} replacement value, "
        f"{_format_currency(settings.UNVERIFIED_MAX_DEPOSIT_CAD)} damage deposit, "
        f"and rentals up to {settings.UNVERIFIED_MAX_BOOKING_DAYS} days."
    )


def unverified_day_limit_error(settings) -> str:
    return (
        f"Unverified renters can book tools for up to {settings.UNVERIFIED_MAX_BOOKING_DAYS} days. "
        "Please shorten your rental or complete ID verification."
    )


def verified_day_limit_error(settings) -> str:
    return (
        f"Bookings are limited to {settings.VERIFIED_MAX_BOOKING_DAYS} days at a time. "
        "Please shorten your rental period."
    )


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
    assert EXPECTED_TOTAL_KEYS <= set(resp.data["totals"].keys())


def test_booking_blocked_for_unverified_high_replacement(unverified_renter_user, listing, settings):
    listing.replacement_value_cad = settings.UNVERIFIED_MAX_REPLACEMENT_CAD + Decimal("100.00")
    listing.save(update_fields=["replacement_value_cad"])
    client = auth(unverified_renter_user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == booking_limit_error_message(settings)


def test_booking_blocked_for_unverified_high_deposit(unverified_renter_user, listing, settings):
    listing.replacement_value_cad = Decimal("500.00")
    listing.damage_deposit_cad = Decimal("850.00")
    listing.save(update_fields=["replacement_value_cad", "damage_deposit_cad"])
    client = auth(unverified_renter_user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=2)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == booking_limit_error_message(settings)


def test_unverified_booking_within_day_limit(unverified_renter_user, listing, settings):
    client = auth(unverified_renter_user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=settings.UNVERIFIED_MAX_BOOKING_DAYS)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 201, resp.data
    assert resp.data["renter"] == unverified_renter_user.id


def test_booking_blocked_for_unverified_excessive_days(unverified_renter_user, listing, settings):
    listing.replacement_value_cad = Decimal("500.00")
    listing.damage_deposit_cad = Decimal("100.00")
    listing.save(update_fields=["replacement_value_cad", "damage_deposit_cad"])
    client = auth(unverified_renter_user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=settings.UNVERIFIED_MAX_BOOKING_DAYS + 1)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == unverified_day_limit_error(settings)


def test_verified_user_can_book_high_value_listing(renter_user, listing, settings):
    listing.replacement_value_cad = Decimal("2000.00")
    listing.damage_deposit_cad = Decimal("900.00")
    listing.save(update_fields=["replacement_value_cad", "damage_deposit_cad"])
    client = auth(renter_user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=settings.VERIFIED_MAX_BOOKING_DAYS)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == Booking.Status.REQUESTED


def test_verified_booking_blocked_when_exceeding_day_limit(renter_user, listing, settings):
    client = auth(renter_user)
    start = date.today() + timedelta(days=1)
    end = start + timedelta(days=settings.VERIFIED_MAX_BOOKING_DAYS + 1)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == verified_day_limit_error(settings)


@pytest.mark.parametrize(
    ("email_verified", "phone_verified"),
    [
        (False, True),
        (True, False),
    ],
)
def test_create_booking_requires_verified_contact(
    renter_user, listing, email_verified, phone_verified
):
    renter_user.email_verified = email_verified
    renter_user.phone_verified = phone_verified
    renter_user.save(update_fields=["email_verified", "phone_verified"])
    client = auth(renter_user)
    start = date.today() + timedelta(days=2)
    end = start + timedelta(days=4)

    resp = client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == (
        "Please verify both your email and phone number before renting tools."
    )


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


def test_cancel_booking_sets_policy_fields(booking_factory, owner_user):
    booking = booking_factory(
        start_date=date.today() + timedelta(days=4),
        end_date=date.today() + timedelta(days=6),
        status=Booking.Status.CONFIRMED,
        auto_canceled=True,
        canceled_reason="previous",
    )
    client = auth(owner_user)
    resp = client.post(
        f"/api/bookings/{booking.id}/cancel/",
        {"reason": "Change of plans"},
        format="json",
    )

    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.OWNER
    assert booking.canceled_reason == "Change of plans"
    assert booking.auto_canceled is False


def test_cancel_pre_payment_booking_uses_mark_helper(monkeypatch, booking_factory, owner_user):
    booking = booking_factory(
        start_date=date.today() + timedelta(days=5),
        end_date=date.today() + timedelta(days=7),
        status=Booking.Status.CONFIRMED,
    )
    booking.charge_payment_intent_id = ""
    booking.save(update_fields=["charge_payment_intent_id", "status"])

    client = auth(owner_user)
    from bookings import api as bookings_api

    call_state = {"count": 0}
    original_mark = bookings_api.mark_canceled

    def fake_mark_canceled(booking_obj, *, actor, auto, reason=None):
        call_state["count"] += 1
        assert actor == "owner"
        assert auto is False
        assert reason == "Need to reschedule"
        original_mark(booking_obj, actor=actor, auto=auto, reason=reason)

    monkeypatch.setattr(bookings_api, "mark_canceled", fake_mark_canceled)

    resp = client.post(
        f"/api/bookings/{booking.id}/cancel/",
        {"reason": "Need to reschedule"},
        format="json",
    )

    assert resp.status_code == 200
    assert call_state["count"] == 1


def test_confirm_booking_recomputes_missing_totals(booking_factory, owner_user):
    start = date.today() + timedelta(days=5)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )
    booking.totals = {}
    booking.save(update_fields=["totals"])

    client = auth(owner_user)
    resp = client.post(f"/api/bookings/{booking.id}/confirm/")
    assert resp.status_code == 200

    booking.refresh_from_db()
    assert booking.status == Booking.Status.CONFIRMED
    assert EXPECTED_TOTAL_KEYS <= set(booking.totals.keys())


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
    window_check_start = timezone.now()
    owner_resp = owner_client.post(f"/api/bookings/{booking.id}/complete/")
    assert owner_resp.status_code == 200
    assert owner_resp.data["status"] == Booking.Status.COMPLETED
    booking.refresh_from_db()
    assert booking.dispute_window_expires_at is not None
    assert window_check_start < booking.dispute_window_expires_at
    assert booking.dispute_window_expires_at < window_check_start + timedelta(hours=25)


def test_complete_does_not_override_existing_dispute_window(booking_factory, owner_user):
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=3)
    existing_window = timezone.now() + timedelta(hours=6)
    booking = booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.CONFIRMED,
        dispute_window_expires_at=existing_window,
    )

    owner_client = auth(owner_user)
    resp = owner_client.post(f"/api/bookings/{booking.id}/complete/")
    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED
    assert booking.dispute_window_expires_at == existing_window


def test_confirm_pickup_sets_timestamp_when_allowed(booking_factory, owner_user):
    start = date.today() + timedelta(days=8)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        before_photos_uploaded_at=timezone.now(),
    )
    BookingPhoto.objects.create(
        booking=booking,
        uploaded_by=booking.renter,
        role=BookingPhoto.Role.BEFORE,
        s3_key="uploads/bookings/test-clean.jpg",
        url="https://cdn.example/before.jpg",
        status=BookingPhoto.Status.ACTIVE,
        av_status=BookingPhoto.AVStatus.CLEAN,
    )
    client = auth(owner_user)
    resp = client.post(f"/api/bookings/{booking.id}/confirm-pickup/")

    assert resp.status_code == 200
    booking.refresh_from_db()
    assert booking.pickup_confirmed_at is not None


def test_confirm_pickup_blocked_without_photos(booking_factory, owner_user, renter_user):
    start = date.today() + timedelta(days=8)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        before_photos_uploaded_at=None,
    )
    renter_client = auth(renter_user)
    renter_resp = renter_client.post(f"/api/bookings/{booking.id}/confirm-pickup/")
    assert renter_resp.status_code == 403

    owner_client = auth(owner_user)
    owner_resp = owner_client.post(f"/api/bookings/{booking.id}/confirm-pickup/")
    assert owner_resp.status_code == 400
    booking.refresh_from_db()
    assert booking.pickup_confirmed_at is None

    booking.before_photos_uploaded_at = timezone.now()
    booking.save(update_fields=["before_photos_uploaded_at"])
    BookingPhoto.objects.create(
        booking=booking,
        uploaded_by=booking.renter,
        role=BookingPhoto.Role.BEFORE,
        s3_key="uploads/bookings/test-pending.jpg",
        url="https://cdn.example/pending.jpg",
        status=BookingPhoto.Status.PENDING,
        av_status=BookingPhoto.AVStatus.PENDING,
    )
    owner_resp = owner_client.post(f"/api/bookings/{booking.id}/confirm-pickup/")
    assert owner_resp.status_code == 400


def test_before_photos_presign_returns_upload_details(
    booking_factory,
    renter_user,
    monkeypatch,
):
    start = date.today() + timedelta(days=5)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
        renter=renter_user,
    )
    client = auth(renter_user)

    def fake_object_key(booking_id, user_id, filename):
        assert booking_id == booking.id
        assert user_id == renter_user.id
        assert filename == "before.png"
        return "uploads/bookings/test-key.png"

    monkeypatch.setattr(bookings_api, "booking_object_key", fake_object_key)

    captured = {}

    def fake_presign(key, content_type, content_md5=None, size_hint=None):
        captured["value"] = (key, content_type, content_md5, size_hint)
        return {"upload_url": "https://s3/upload", "headers": {"Content-Type": content_type}}

    monkeypatch.setattr(bookings_api, "presign_put", fake_presign)

    payload = {
        "filename": "before.png",
        "content_type": "image/png",
        "size": 1024,
        "content_md5": "abcd==",
    }
    resp = client.post(
        f"/api/bookings/{booking.id}/before-photos/presign/",
        payload,
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["key"] == "uploads/bookings/test-key.png"
    assert resp.data["upload_url"] == "https://s3/upload"
    assert resp.data["tagging"] == "av-status=pending"
    assert captured["value"][3] == 1024


def test_before_photos_complete_creates_photo_and_schedules_scan(
    booking_factory,
    renter_user,
    monkeypatch,
):
    start = date.today() + timedelta(days=4)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
        renter=renter_user,
    )
    client = auth(renter_user)

    monkeypatch.setattr(bookings_api, "public_url", lambda key: f"https://cdn.example/{key}")

    queued = {}

    class _StubTask:
        def delay(self, **kwargs):
            queued.update(kwargs)

    monkeypatch.setattr(bookings_api, "scan_and_finalize_booking_photo", _StubTask())

    payload = {
        "key": "uploads/bookings/manual/before.jpg",
        "etag": '"etag-1234"',
        "filename": "before.jpg",
        "content_type": "image/jpeg",
        "size": 2048,
    }
    resp = client.post(
        f"/api/bookings/{booking.id}/before-photos/complete/",
        payload,
        format="json",
    )

    assert resp.status_code == 202, resp.data
    photo = BookingPhoto.objects.get(booking=booking, s3_key=payload["key"])
    assert photo.url == f"https://cdn.example/{payload['key']}"
    assert photo.status == BookingPhoto.Status.PENDING
    assert photo.av_status == BookingPhoto.AVStatus.PENDING
    assert queued["key"] == payload["key"]
    assert queued["booking_id"] == booking.id
    assert queued["uploaded_by_id"] == renter_user.id
    assert queued["meta"]["role"] == BookingPhoto.Role.BEFORE
    booking.refresh_from_db()
    assert booking.before_photos_uploaded_at is not None


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


def test_status_label_shows_in_progress_after_pickup(
    booking_factory,
    renter_user,
):
    start = date.today() + timedelta(days=3)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        renter=renter_user,
        pickup_confirmed_at=timezone.now(),
    )
    client = auth(renter_user)
    resp = client.get("/api/bookings/my/")
    assert resp.status_code == 200
    returned = {item["id"]: item for item in resp.data}
    assert returned[booking.id]["status_label"] == "In progress"


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
    assert resp.data["unpaid_bookings"] == 1


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
    assert resp.data["unpaid_bookings"] == 0


def test_pending_requests_count_reports_unpaid_confirmed_bookings(
    booking_factory,
    owner_user,
):
    start = date.today() + timedelta(days=2)
    booking_factory(
        start_date=start,
        end_date=start + timedelta(days=3),
        status=Booking.Status.CONFIRMED,
    )
    booking_factory(
        start_date=start + timedelta(days=4),
        end_date=start + timedelta(days=6),
        status=Booking.Status.CONFIRMED,
    )
    paid_booking = booking_factory(
        start_date=start + timedelta(days=7),
        end_date=start + timedelta(days=9),
        status=Booking.Status.CONFIRMED,
    )
    paid_booking.charge_payment_intent_id = "pi_paid"
    paid_booking.save(update_fields=["charge_payment_intent_id"])

    client = auth(owner_user)
    resp = client.get("/api/bookings/pending-requests-count/")
    assert resp.status_code == 200
    assert resp.data["pending_requests"] == 0
    assert resp.data["unpaid_bookings"] == 2


def test_pending_requests_count_reports_renter_unpaid_bookings(
    booking_factory,
    renter_user,
    owner_user,
):
    start = date.today() + timedelta(days=5)
    booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.CONFIRMED,
        renter=renter_user,
        owner=owner_user,
    )
    booking_factory(
        start_date=start + timedelta(days=4),
        end_date=start + timedelta(days=5),
        status=Booking.Status.PAID,
        renter=renter_user,
        owner=owner_user,
    )

    client = auth(renter_user)
    resp = client.get("/api/bookings/pending-requests-count/")
    assert resp.status_code == 200
    assert resp.data["pending_requests"] == 0
    assert resp.data["unpaid_bookings"] == 0
    assert resp.data["renter_unpaid_bookings"] == 1


def test_pending_requests_count_ignores_unpaid_bookings_for_other_owners(
    owner_user,
    other_user,
):
    start = date.today() + timedelta(days=10)
    other_listing = Listing.objects.create(
        owner=other_user,
        title="Other Tool",
        description="Useful tool",
        daily_price_cad=Decimal("15.00"),
        replacement_value_cad=Decimal("200.00"),
        damage_deposit_cad=Decimal("75.00"),
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
        status=Booking.Status.CONFIRMED,
    )

    client = auth(owner_user)
    resp = client.get("/api/bookings/pending-requests-count/")
    assert resp.status_code == 200
    assert resp.data["unpaid_bookings"] == 0


def test_requested_booking_does_not_block_availability(booking_factory, listing):
    start = date.today() + timedelta(days=10)
    booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.REQUESTED,
    )

    client = APIClient()
    resp = client.get(f"/api/bookings/availability/?listing={listing.id}")
    assert resp.status_code == 200
    assert resp.data == []


def test_availability_returns_blocking_bookings_for_listing(
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


def test_overlapping_requested_bookings_allowed_but_confirm_conflicts_blocked(
    booking_factory,
    listing,
    other_user,
    owner_user,
):
    start = date.today() + timedelta(days=6)
    end = start + timedelta(days=3)
    booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.REQUESTED,
    )

    other_client = auth(other_user)
    resp = other_client.post("/api/bookings/", booking_payload(listing, start, end), format="json")

    assert resp.status_code == 201, resp.data
    assert resp.data["status"] == Booking.Status.REQUESTED

    blocking_start = date.today() + timedelta(days=20)
    blocking_end = blocking_start + timedelta(days=4)
    booking_factory(
        start_date=blocking_start,
        end_date=blocking_end,
        status=Booking.Status.CONFIRMED,
    )
    overlap_booking = booking_factory(
        start_date=blocking_start + timedelta(days=1),
        end_date=blocking_end + timedelta(days=1),
        status=Booking.Status.REQUESTED,
    )

    owner_client = auth(owner_user)
    conflict_resp = owner_client.post(f"/api/bookings/{overlap_booking.id}/confirm/")
    assert conflict_resp.status_code == 400
    assert "not available" in conflict_resp.data["non_field_errors"][0]


def test_mark_late_charges_extra_days_and_logs_ledgers(
    booking_factory,
    owner_user,
    renter_user,
    other_user,
    monkeypatch,
    settings,
):
    start = date(2025, 1, 1)
    end = start + timedelta(days=2)
    booking = booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.PAID,
    )
    booking.totals = compute_booking_totals(
        listing=booking.listing,
        start_date=start,
        end_date=end,
    )
    booking.save(update_fields=["totals"])
    settings.PLATFORM_LEDGER_USER_ID = other_user.id

    fixed_today = end + timedelta(days=3)
    monkeypatch.setattr(bookings_api.timezone, "localdate", lambda: fixed_today)

    captured_amount = {}

    def fake_create_late_fee_payment_intent(*, booking, amount, description=""):
        captured_amount["value"] = amount
        log_transaction(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.BOOKING_CHARGE,
            amount=amount,
        )
        return "pi_late_test"

    monkeypatch.setattr(
        bookings_api,
        "create_late_fee_payment_intent",
        fake_create_late_fee_payment_intent,
    )

    owner_client = auth(owner_user)
    resp = owner_client.post(f"/api/bookings/{booking.id}/mark-late/")

    assert resp.status_code == 200, resp.data
    assert resp.data["late_fee_days"] == 2
    assert resp.data["late_fee_amount"] == "99.00"
    assert captured_amount["value"] == Decimal("99.00")

    owner_txn = Transaction.objects.get(kind=Transaction.Kind.OWNER_EARNING)
    platform_txn = Transaction.objects.get(kind=Transaction.Kind.PLATFORM_FEE)
    charge_txn = Transaction.objects.get(kind=Transaction.Kind.BOOKING_CHARGE)

    assert owner_txn.user_id == owner_user.id
    assert owner_txn.amount == Decimal("85.50")
    assert platform_txn.user_id == other_user.id
    assert platform_txn.amount == Decimal("13.50")
    assert charge_txn.amount == Decimal("99.00")


def test_mark_not_returned_captures_deposit_amount(
    booking_factory,
    owner_user,
    renter_user,
    monkeypatch,
):
    start = date(2025, 2, 1)
    end = start + timedelta(days=3)
    booking = booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.PAID,
        pickup_confirmed_at=timezone.now() - timedelta(days=5),
        deposit_hold_id="pi_deposit_existing",
    )
    booking.totals = compute_booking_totals(
        listing=booking.listing,
        start_date=start,
        end_date=end,
    )
    booking.save(update_fields=["totals"])

    fixed_today = end + timedelta(days=4)
    monkeypatch.setattr(bookings_api.timezone, "localdate", lambda: fixed_today)

    captured_amount = {}

    def fake_capture_deposit_amount(*, booking, amount):
        captured_amount["value"] = amount
        log_transaction(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
            amount=amount,
        )
        return booking.deposit_hold_id

    monkeypatch.setattr(bookings_api, "capture_deposit_amount", fake_capture_deposit_amount)

    owner_client = auth(owner_user)
    resp = owner_client.post(
        f"/api/bookings/{booking.id}/mark-not-returned/",
        {"amount": "40.00"},
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["deposit_captured"] == "40.00"
    assert captured_amount["value"] == Decimal("40.00")

    deposit_txn = Transaction.objects.get(kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE)
    assert deposit_txn.amount == Decimal("40.00")
