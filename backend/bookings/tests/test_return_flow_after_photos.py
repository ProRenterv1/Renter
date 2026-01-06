"""Tests for return flow and after-photos endpoints."""

from __future__ import annotations

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings import api as bookings_api
from bookings.models import Booking, BookingPhoto
from storage.s3 import booking_object_key
from storage.tasks import _finalize_booking_photo_record

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


def test_renter_return_happy_path(booking_factory, renter_user):
    today = timezone.localdate()
    start = today - timedelta(days=3)
    end = today
    booking = booking_factory(
        start_date=start,
        end_date=end,
        status=Booking.Status.PAID,
        renter=renter_user,
        pickup_confirmed_at=timezone.now() - timedelta(days=1),
    )
    client = auth(renter_user)

    resp = client.post(f"/api/bookings/{booking.id}/renter-return/", {}, format="json")

    assert resp.status_code == 200, resp.data
    assert resp.data["returned_by_renter_at"] is not None
    booking.refresh_from_db()
    assert booking.returned_by_renter_at is not None
    assert booking.status == Booking.Status.PAID


def test_renter_return_forbidden_for_non_renter(booking_factory, owner_user):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today - timedelta(days=4),
        end_date=today - timedelta(days=1),
        status=Booking.Status.PAID,
        pickup_confirmed_at=timezone.now(),
    )
    client = auth(owner_user)

    resp = client.post(f"/api/bookings/{booking.id}/renter-return/", {}, format="json")

    assert resp.status_code == 403
    assert "renter" in (resp.data.get("detail") or "").lower()


@pytest.mark.parametrize(
    "status_value,pickup_confirmed_at,end_offset_days,expected_message",
    [
        (Booking.Status.CONFIRMED, timezone.now(), -1, "in progress"),
        (Booking.Status.PAID, None, -1, "in progress"),
        (Booking.Status.PAID, timezone.now(), 1, "past its end date"),
    ],
)
def test_renter_return_preconditions(
    booking_factory,
    renter_user,
    status_value,
    pickup_confirmed_at,
    end_offset_days,
    expected_message,
):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today - timedelta(days=2),
        end_date=today + timedelta(days=end_offset_days),
        status=status_value,
        renter=renter_user,
        pickup_confirmed_at=pickup_confirmed_at,
    )
    client = auth(renter_user)

    resp = client.post(f"/api/bookings/{booking.id}/renter-return/", {}, format="json")

    assert resp.status_code == 400
    assert expected_message in (resp.data.get("detail") or "")


def test_owner_mark_returned_happy_path(booking_factory, owner_user, renter_user):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today - timedelta(days=5),
        end_date=today - timedelta(days=2),
        status=Booking.Status.PAID,
        renter=renter_user,
        pickup_confirmed_at=timezone.now() - timedelta(days=3),
        returned_by_renter_at=timezone.now() - timedelta(hours=2),
    )
    client = auth(owner_user)

    resp = client.post(f"/api/bookings/{booking.id}/owner-mark-returned/", {}, format="json")

    assert resp.status_code == 200, resp.data
    booking.refresh_from_db()
    assert booking.return_confirmed_at is not None
    assert booking.status == Booking.Status.PAID
    assert booking.returned_by_renter_at is not None


def test_owner_mark_returned_forbidden_for_non_owner(booking_factory, renter_user):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today - timedelta(days=4),
        end_date=today - timedelta(days=1),
        status=Booking.Status.PAID,
        renter=renter_user,
        pickup_confirmed_at=timezone.now(),
        returned_by_renter_at=timezone.now(),
    )
    client = auth(renter_user)

    resp = client.post(f"/api/bookings/{booking.id}/owner-mark-returned/", {}, format="json")

    assert resp.status_code == 403


@pytest.mark.parametrize(
    "status_value,returned_at,expected_message",
    [
        (Booking.Status.CONFIRMED, timezone.now(), "paid state"),
        (Booking.Status.PAID, None, "mark return"),
    ],
)
def test_owner_mark_returned_preconditions(
    booking_factory, owner_user, renter_user, status_value, returned_at, expected_message
):
    today = timezone.localdate()
    booking = booking_factory(
        start_date=today - timedelta(days=3),
        end_date=today - timedelta(days=1),
        status=status_value,
        renter=renter_user,
        pickup_confirmed_at=timezone.now(),
        returned_by_renter_at=returned_at,
    )
    client = auth(owner_user)

    resp = client.post(f"/api/bookings/{booking.id}/owner-mark-returned/", {}, format="json")

    assert resp.status_code == 400
    assert expected_message in (resp.data.get("detail") or "")


def test_after_photos_presign_happy_path(booking_factory, renter_user, monkeypatch, settings):
    settings.S3_MAX_UPLOAD_BYTES = 10_000
    start = timezone.localdate() - timedelta(days=1)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    client = auth(renter_user)

    def fake_object_key(booking_id, user_id, filename):
        assert booking_id == booking.id
        assert user_id == renter_user.id
        assert filename == "after.jpg"
        return f"uploads/bookings/{booking_id}/{user_id}/after.jpg"

    monkeypatch.setattr(bookings_api, "booking_object_key", fake_object_key)
    monkeypatch.setattr(
        bookings_api,
        "presign_put",
        lambda key, content_type, content_md5=None, size_hint=None: {
            "upload_url": "https://s3/upload",
            "headers": {"Content-Type": content_type},
        },
    )

    payload = {"filename": "after.jpg", "size": 1024, "content_type": "image/jpeg"}
    resp = client.post(
        f"/api/bookings/{booking.id}/after-photos/presign/",
        payload,
        format="json",
    )

    assert resp.status_code == 200, resp.data
    assert resp.data["key"].startswith(f"uploads/bookings/{booking.id}/{renter_user.id}/")
    assert resp.data["upload_url"] == "https://s3/upload"
    assert resp.data["tagging"] == "av-status=pending"
    assert "headers" in resp.data


def test_after_photos_complete_queues_scan(booking_factory, renter_user, monkeypatch, settings):
    settings.S3_MAX_UPLOAD_BYTES = 10_000
    start = timezone.localdate() - timedelta(days=1)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=3),
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    client = auth(renter_user)

    monkeypatch.setattr(bookings_api, "public_url", lambda key: f"https://cdn.test/{key}")

    queued = {}

    class _StubTask:
        def delay(self, **kwargs):
            queued.update(kwargs)

    monkeypatch.setattr(bookings_api, "scan_and_finalize_booking_photo", _StubTask())

    payload = {
        "key": booking_object_key(booking.id, renter_user.id, "after.png"),
        "etag": '"etag-after"',
        "filename": "after.png",
        "content_type": "image/png",
        "size": 4096,
    }
    resp = client.post(
        f"/api/bookings/{booking.id}/after-photos/complete/",
        payload,
        format="json",
    )

    assert resp.status_code == 202, resp.data
    assert resp.data["status"] == "queued"
    assert queued["key"] == payload["key"]
    assert queued["booking_id"] == booking.id
    assert queued["uploaded_by_id"] == renter_user.id
    assert queued["meta"]["role"] == BookingPhoto.Role.AFTER
    assert queued["meta"]["etag"] == payload["etag"]
    photo = BookingPhoto.objects.get(booking=booking, s3_key=payload["key"])
    assert photo.role == BookingPhoto.Role.AFTER
    assert photo.url == f"https://cdn.test/{payload['key']}"
    assert photo.status == BookingPhoto.Status.PENDING
    assert photo.av_status == BookingPhoto.AVStatus.PENDING


@pytest.mark.parametrize(
    "endpoint,method_payload",
    [
        ("after-photos/presign", {"filename": "x.jpg", "size": 10, "content_type": "image/jpeg"}),
        ("after-photos/complete", {"key": "k", "etag": "e", "size": 10}),
    ],
)
def test_after_photos_permissions(
    endpoint, method_payload, booking_factory, owner_user, renter_user
):
    start = timezone.localdate()
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=1),
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    client = auth(owner_user)

    resp = client.post(f"/api/bookings/{booking.id}/{endpoint}/", method_payload, format="json")

    # Owners are allowed to handle after-photos; ensure access works
    assert resp.status_code in {200, 202}


@pytest.mark.parametrize(
    "endpoint,method_payload",
    [
        ("after-photos/presign", {"filename": "x.jpg", "size": 10, "content_type": "image/jpeg"}),
        ("after-photos/complete", {"key": "k", "etag": "e", "size": 10}),
    ],
)
def test_after_photos_blocked_for_terminal_bookings(
    endpoint, method_payload, booking_factory, renter_user
):
    start = timezone.localdate()
    booking = booking_factory(
        start_date=start - timedelta(days=2),
        end_date=start - timedelta(days=1),
        status=Booking.Status.COMPLETED,
        renter=renter_user,
    )
    client = auth(renter_user)

    resp = client.post(f"/api/bookings/{booking.id}/{endpoint}/", method_payload, format="json")

    assert resp.status_code == 400


@pytest.mark.parametrize(
    "payload,expected_message",
    [
        ({"filename": "a.jpg", "content_type": "image/jpeg"}, "size is required"),
        ({"filename": "a.jpg", "content_type": "image/jpeg", "size": "bad"}, "must be an integer"),
    ],
)
def test_after_photos_presign_validations(payload, expected_message, booking_factory, renter_user):
    start = timezone.localdate()
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    client = auth(renter_user)

    resp = client.post(
        f"/api/bookings/{booking.id}/after-photos/presign/",
        payload,
        format="json",
    )

    assert resp.status_code == 400
    assert expected_message in (resp.data.get("detail") or "")


def test_after_photos_presign_rejects_oversized_upload(booking_factory, renter_user, settings):
    settings.S3_MAX_UPLOAD_BYTES = 50
    start = timezone.localdate()
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    client = auth(renter_user)

    resp = client.post(
        f"/api/bookings/{booking.id}/after-photos/presign/",
        {"filename": "a.jpg", "size": 51, "content_type": "image/jpeg"},
        format="json",
    )

    assert resp.status_code == 400
    assert "File too large" in (resp.data.get("detail") or "")


def test_after_photos_complete_requires_valid_size(booking_factory, renter_user):
    start = timezone.localdate()
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=1),
        status=Booking.Status.PAID,
        renter=renter_user,
    )
    client = auth(renter_user)

    resp = client.post(
        f"/api/bookings/{booking.id}/after-photos/complete/",
        {"key": "k", "etag": "e", "size": "bad"},
        format="json",
    )

    assert resp.status_code == 400
    assert "must be an integer" in (resp.data.get("detail") or "")


def test_finalize_after_photo_sets_completed(booking_factory, renter_user, monkeypatch):
    monkeypatch.setattr("storage.tasks.push_event", lambda *args, **kwargs: None)
    status_email_calls: list[tuple] = []
    review_email_calls: list[tuple] = []

    monkeypatch.setattr(
        "notifications.tasks.send_booking_status_email.delay",
        lambda *args, **kwargs: status_email_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "notifications.tasks.send_booking_completed_review_invite_email.delay",
        lambda *args, **kwargs: review_email_calls.append((args, kwargs)),
    )
    start = timezone.localdate() - timedelta(days=3)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.PAID,
        renter=renter_user,
        pickup_confirmed_at=timezone.now(),
    )
    meta = {
        "etag": "abc",
        "filename": "after.jpg",
        "content_type": "image/jpeg",
        "size": 100,
        "role": BookingPhoto.Role.AFTER,
    }

    now = timezone.now()
    _finalize_booking_photo_record(
        booking_id=booking.id,
        uploaded_by_id=renter_user.id,
        key="after/key",
        verdict="clean",
        meta=meta,
        dimensions=(800, 600),
    )

    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED
    assert booking.after_photos_uploaded_at is not None
    assert booking.dispute_window_expires_at > now
    assert booking.dispute_window_expires_at < now + timedelta(hours=25)
    expected_release = timezone.make_aware(
        datetime.combine(booking.end_date + timedelta(days=1), time.min),
        timezone.get_current_timezone(),
    )
    assert booking.deposit_release_scheduled_at == expected_release

    photo = BookingPhoto.objects.filter(booking=booking).order_by("-id").first()
    assert photo.role == BookingPhoto.Role.AFTER
    assert photo.status == BookingPhoto.Status.ACTIVE
    assert photo.av_status == BookingPhoto.AVStatus.CLEAN
    assert photo.filename == meta["filename"]

    assert status_email_calls == [((renter_user.id, booking.id, Booking.Status.COMPLETED), {})]
    assert review_email_calls == [((booking.id,), {})]


def test_finalize_after_photo_idempotent_when_already_completed(
    booking_factory, renter_user, monkeypatch
):
    monkeypatch.setattr("storage.tasks.push_event", lambda *args, **kwargs: None)
    status_email_calls: list[tuple] = []
    review_email_calls: list[tuple] = []
    monkeypatch.setattr(
        "notifications.tasks.send_booking_status_email.delay",
        lambda *args, **kwargs: status_email_calls.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "notifications.tasks.send_booking_completed_review_invite_email.delay",
        lambda *args, **kwargs: review_email_calls.append((args, kwargs)),
    )
    start = timezone.localdate() - timedelta(days=4)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=2),
        status=Booking.Status.COMPLETED,
        renter=renter_user,
        pickup_confirmed_at=timezone.now() - timedelta(days=1),
        after_photos_uploaded_at=timezone.now() - timedelta(hours=1),
        dispute_window_expires_at=timezone.now() + timedelta(hours=20),
        deposit_release_scheduled_at=timezone.make_aware(
            datetime.combine(start + timedelta(days=3), time.min),
            timezone.get_current_timezone(),
        ),
    )
    meta = {
        "etag": "def",
        "filename": "after2.jpg",
        "content_type": "image/jpeg",
        "size": 120,
        "role": BookingPhoto.Role.AFTER,
    }
    original_updated = booking.updated_at
    original_after = booking.after_photos_uploaded_at
    original_dispute = booking.dispute_window_expires_at
    original_release = booking.deposit_release_scheduled_at
    _finalize_booking_photo_record(
        booking_id=booking.id,
        uploaded_by_id=renter_user.id,
        key="after/key2",
        verdict="clean",
        meta=meta,
        dimensions=(640, 480),
    )

    booking.refresh_from_db()
    assert booking.status == Booking.Status.COMPLETED
    assert booking.after_photos_uploaded_at == original_after
    assert booking.dispute_window_expires_at == original_dispute
    assert booking.deposit_release_scheduled_at == original_release
    assert booking.updated_at >= original_updated

    assert status_email_calls == []
    assert review_email_calls == []


def test_finalize_infected_after_photo_does_not_complete(booking_factory, renter_user, monkeypatch):
    monkeypatch.setattr("storage.tasks.push_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "notifications.tasks.send_booking_status_email.delay", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "notifications.tasks.send_booking_completed_review_invite_email.delay",
        lambda *args, **kwargs: None,
    )
    start = timezone.localdate() - timedelta(days=2)
    booking = booking_factory(
        start_date=start,
        end_date=start + timedelta(days=1),
        status=Booking.Status.PAID,
        renter=renter_user,
        pickup_confirmed_at=timezone.now(),
    )
    meta = {
        "etag": "ghi",
        "filename": "after3.jpg",
        "content_type": "image/jpeg",
        "size": 200,
        "role": BookingPhoto.Role.AFTER,
    }

    _finalize_booking_photo_record(
        booking_id=booking.id,
        uploaded_by_id=renter_user.id,
        key="after/key3",
        verdict="infected",
        meta=meta,
        dimensions=(320, 240),
    )

    booking.refresh_from_db()
    assert booking.status == Booking.Status.PAID
    assert booking.after_photos_uploaded_at is None
    assert booking.dispute_window_expires_at is None
    assert booking.deposit_release_scheduled_at is None

    photo = BookingPhoto.objects.filter(booking=booking, s3_key="after/key3").first()
    assert photo is not None
    assert photo.status == BookingPhoto.Status.BLOCKED
    assert photo.av_status == BookingPhoto.AVStatus.INFECTED
