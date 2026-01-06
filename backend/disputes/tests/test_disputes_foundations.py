"""Tests for dispute creation, messaging, evidence uploads, and deposit locks."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from bookings.models import Booking
from bookings.tasks import auto_release_deposits
from disputes.models import DisputeCase, DisputeEvidence, DisputeMessage
from payments import stripe_api
from payments.models import Transaction

User = get_user_model()

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff_user():
    return User.objects.create_user(
        username="staff",
        password="testpass",
        is_staff=True,
        is_superuser=True,
        can_list=True,
        can_rent=True,
        email_verified=True,
        phone_verified=True,
    )


@pytest.fixture
def stripe_intent_stub(monkeypatch):
    state: dict[str, object] = {"status": "requires_capture", "cancel_calls": []}

    def fake_retrieve(intent_id: str):
        return SimpleNamespace(id=intent_id, status=state["status"])

    def fake_cancel(intent_id: str):
        state["cancel_calls"].append(intent_id)
        return SimpleNamespace(id=intent_id, status="canceled")

    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "retrieve", fake_retrieve)
    monkeypatch.setattr(stripe_api.stripe.PaymentIntent, "cancel", fake_cancel)
    return state


def _create_booking_with_deposit(booking_factory, *, owner=None, renter=None) -> Booking:
    today = timezone.localdate()
    return booking_factory(
        owner=owner,
        renter=renter,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        deposit_hold_id="pi_test_hold",
        dispute_window_expires_at=timezone.now() + timedelta(hours=1),
        totals={"damage_deposit": "50.00"},
    )


@pytest.mark.parametrize(
    "status",
    [
        Booking.Status.REQUESTED,
        Booking.Status.CONFIRMED,
        Booking.Status.CANCELED,
    ],
)
@pytest.mark.parametrize("actor", ["renter", "owner"])
def test_dispute_rejected_when_booking_not_paid_or_completed(
    api_client, booking_factory, renter_user, owner_user, status, actor
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        owner=owner_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=status,
        dispute_window_expires_at=timezone.now() + timedelta(hours=1),
    )
    user = renter_user if actor == "renter" else owner_user
    api_client.force_authenticate(user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Invalid status",
        },
        format="json",
    )

    assert resp.status_code == 400
    assert "paid or recently completed" in "".join(resp.json().get("non_field_errors", []))


@pytest.mark.parametrize("status", [Booking.Status.PAID, Booking.Status.COMPLETED])
def test_dispute_allowed_for_paid_or_completed_inside_window(
    api_client, booking_factory, renter_user, status
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=status,
        dispute_window_expires_at=timezone.now() + timedelta(hours=2),
    )
    api_client.force_authenticate(renter_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Valid dispute",
        },
        format="json",
    )

    assert resp.status_code == 201
    assert DisputeCase.objects.filter(booking=booking, opened_by=renter_user).count() == 1


def test_dispute_rejected_when_window_expired_non_safety(api_client, booking_factory, renter_user):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.COMPLETED,
        dispute_window_expires_at=timezone.now() - timedelta(hours=1),
    )
    api_client.force_authenticate(renter_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Too late",
        },
        format="json",
    )

    assert resp.status_code == 400
    assert "Dispute window expired" in "".join(resp.json().get("non_field_errors", []))


def test_dispute_allowed_when_safety_or_fraud_even_if_expired(
    api_client, booking_factory, renter_user
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        dispute_window_expires_at=timezone.now() - timedelta(hours=1),
    )
    api_client.force_authenticate(renter_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.SAFETY_OR_FRAUD,
            "description": "Safety report",
        },
        format="json",
    )

    assert resp.status_code == 201
    assert DisputeCase.objects.filter(booking=booking, opened_by=renter_user).count() == 1


def test_dispute_sets_booking_is_disputed_and_deposit_locked(
    api_client, booking_factory, renter_user
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        dispute_window_expires_at=timezone.now() + timedelta(hours=1),
        deposit_hold_id="pi_deposit_test",
        deposit_locked=False,
        totals={"damage_deposit": "15.00"},
    )
    api_client.force_authenticate(renter_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Damage with deposit",
        },
        format="json",
    )

    assert resp.status_code == 201
    dispute = DisputeCase.objects.get(id=resp.json()["id"])
    booking.refresh_from_db()
    assert booking.is_disputed is True
    assert booking.deposit_locked is True
    assert dispute.deposit_locked is True


def test_staff_can_file_dispute_outside_window(
    api_client, booking_factory, staff_user, renter_user, owner_user
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        owner=owner_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        dispute_window_expires_at=timezone.now() - timedelta(hours=2),
    )
    api_client.force_authenticate(staff_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Staff override",
        },
        format="json",
    )

    assert resp.status_code == 201
    assert DisputeCase.objects.filter(booking=booking, opened_by=staff_user).count() == 1


def test_dispute_creation_sets_flags_renter(api_client, booking_factory, renter_user):
    booking = _create_booking_with_deposit(booking_factory, renter=renter_user)
    api_client.force_authenticate(renter_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Broken item",
        },
        format="json",
    )
    assert resp.status_code == 201
    dispute_id = resp.json()["id"]
    dispute = DisputeCase.objects.get(id=dispute_id)
    assert dispute.opened_by_id == renter_user.id
    assert dispute.opened_by_role == DisputeCase.OpenedByRole.RENTER
    assert dispute.status in {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
    }
    assert dispute.deposit_locked is True

    booking.refresh_from_db()
    assert booking.is_disputed is True
    assert booking.deposit_locked is True


def test_dispute_creation_sets_flags_owner(api_client, booking_factory, owner_user):
    booking = _create_booking_with_deposit(booking_factory, owner=owner_user)
    api_client.force_authenticate(owner_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Owner filed dispute",
        },
        format="json",
    )
    assert resp.status_code == 201
    dispute = DisputeCase.objects.get(id=resp.json()["id"])
    assert dispute.opened_by_id == owner_user.id
    assert dispute.opened_by_role == DisputeCase.OpenedByRole.OWNER
    assert dispute.status in {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
    }

    booking.refresh_from_db()
    assert booking.is_disputed is True
    assert booking.deposit_locked is True


def test_dispute_permissions_and_messages(
    api_client, booking_factory, renter_user, owner_user, other_user, staff_user
):
    booking = _create_booking_with_deposit(booking_factory, renter=renter_user, owner=owner_user)
    api_client.force_authenticate(renter_user)
    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Initial dispute",
        },
        format="json",
    )
    assert resp.status_code == 201
    dispute_id = resp.json()["id"]

    # renter can view
    assert api_client.get(f"/api/disputes/{dispute_id}/").status_code == 200
    # owner can view
    api_client.force_authenticate(owner_user)
    assert api_client.get(f"/api/disputes/{dispute_id}/").status_code == 200
    # staff can view
    api_client.force_authenticate(staff_user)
    assert api_client.get(f"/api/disputes/{dispute_id}/").status_code == 200
    # unrelated user forbidden
    api_client.force_authenticate(other_user)
    assert api_client.get(f"/api/disputes/{dispute_id}/").status_code == 403

    # messages set correct roles
    api_client.force_authenticate(renter_user)
    msg_renter = api_client.post(
        f"/api/disputes/{dispute_id}/messages/",
        {"text": "from renter"},
        format="json",
    )
    assert msg_renter.status_code == 201
    assert DisputeMessage.objects.get(id=msg_renter.json()["id"]).role == DisputeMessage.Role.RENTER

    api_client.force_authenticate(owner_user)
    msg_owner = api_client.post(
        f"/api/disputes/{dispute_id}/messages/",
        {"text": "from owner"},
        format="json",
    )
    assert msg_owner.status_code == 201
    assert DisputeMessage.objects.get(id=msg_owner.json()["id"]).role == DisputeMessage.Role.OWNER

    api_client.force_authenticate(staff_user)
    msg_staff = api_client.post(
        f"/api/disputes/{dispute_id}/messages/",
        {"text": "from staff"},
        format="json",
    )
    assert msg_staff.status_code == 201
    assert DisputeMessage.objects.get(id=msg_staff.json()["id"]).role == DisputeMessage.Role.ADMIN

    # unrelated user cannot post messages
    api_client.force_authenticate(other_user)
    assert (
        api_client.post(
            f"/api/disputes/{dispute_id}/messages/",
            {"text": "blocked"},
            format="json",
        ).status_code
        == 403
    )


def test_evidence_presign_and_complete(
    api_client, booking_factory, renter_user, monkeypatch, settings
):
    booking = _create_booking_with_deposit(booking_factory, renter=renter_user)
    api_client.force_authenticate(renter_user)
    settings.S3_MAX_UPLOAD_BYTES = 1024

    calls = {}

    def fake_presign(key, **kwargs):
        calls["presign"] = {"key": key, "kwargs": kwargs}
        return {"upload_url": "https://upload.test/presigned", "headers": {"X-Test": "1"}}

    def fake_delay(*, key, dispute_id, uploaded_by_id, meta):
        calls["delay"] = {
            "key": key,
            "dispute_id": dispute_id,
            "uploaded_by_id": uploaded_by_id,
            "meta": meta,
        }
        return None

    monkeypatch.setattr("disputes.api.presign_put", fake_presign)
    monkeypatch.setattr("disputes.api.scan_and_finalize_dispute_evidence.delay", fake_delay)

    # create dispute
    create_resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Broken",
        },
        format="json",
    )
    assert create_resp.status_code == 201
    dispute_id = create_resp.json()["id"]

    presign_resp = api_client.post(
        f"/api/disputes/{dispute_id}/evidence/presign/",
        {"filename": "proof.jpg", "content_type": "image/jpeg", "size": 500},
        format="json",
    )
    assert presign_resp.status_code == 200
    presign_data = presign_resp.json()
    assert presign_data["upload_url"] == "https://upload.test/presigned"
    assert presign_data["headers"] == {"X-Test": "1"}
    assert presign_data["tagging"] == "av-status=pending"
    key = presign_data["key"]

    complete_resp = api_client.post(
        f"/api/disputes/{dispute_id}/evidence/complete/",
        {
            "key": key,
            "etag": '"etag123"',
            "size": 500,
            "filename": "proof.jpg",
            "content_type": "image/jpeg",
            "kind": DisputeEvidence.Kind.VIDEO,
        },
        format="json",
    )
    assert complete_resp.status_code == 202
    assert complete_resp.json()["status"] == "queued"

    evidence = DisputeEvidence.objects.get(
        dispute_id=dispute_id, uploaded_by=renter_user, s3_key=key
    )
    assert evidence.av_status == DisputeEvidence.AVStatus.PENDING
    assert evidence.kind == DisputeEvidence.Kind.VIDEO
    assert calls["delay"]["key"] == key
    assert calls["delay"]["dispute_id"] == dispute_id
    assert calls["delay"]["uploaded_by_id"] == renter_user.id
    assert calls["delay"]["meta"]["etag"] == '"etag123"'


def test_auto_release_deposits_respects_deposit_locked(
    booking_factory, stripe_intent_stub, renter_user, owner_user, settings
):
    settings.STRIPE_SECRET_KEY = "sk_test_123"
    now = timezone.now()
    booking_release = booking_factory(
        renter=renter_user,
        owner=owner_user,
        start_date=now.date(),
        end_date=now.date() + timedelta(days=1),
        status=Booking.Status.COMPLETED,
        deposit_hold_id="pi_release",
        deposit_release_scheduled_at=now - timedelta(hours=1),
        dispute_window_expires_at=None,
        deposit_locked=False,
        totals={"damage_deposit": "25.00"},
    )
    booking_locked = booking_factory(
        renter=renter_user,
        owner=owner_user,
        start_date=now.date(),
        end_date=now.date() + timedelta(days=1),
        status=Booking.Status.COMPLETED,
        deposit_hold_id="pi_locked",
        deposit_release_scheduled_at=now - timedelta(hours=1),
        dispute_window_expires_at=None,
        deposit_locked=True,
        totals={"damage_deposit": "25.00"},
    )

    released = auto_release_deposits()

    assert released == 1
    booking_release.refresh_from_db()
    booking_locked.refresh_from_db()
    assert booking_release.deposit_released_at is not None
    assert booking_locked.deposit_released_at is None
    assert booking_locked.deposit_hold_id == "pi_locked"
    assert (
        Transaction.objects.filter(
            booking=booking_release,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
            stripe_id="pi_release",
        ).count()
        == 1
    )
    assert (
        Transaction.objects.filter(
            booking=booking_locked,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        ).count()
        == 0
    )
    assert stripe_intent_stub["cancel_calls"] == ["pi_release"]
