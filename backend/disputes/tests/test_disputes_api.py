"""API-level tests for dispute creation flows."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking
from disputes.models import DisputeCase, DisputeEvidence

pytestmark = pytest.mark.django_db


def test_completed_booking_rejected_when_window_expired(api_client, booking_factory, renter_user):
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
            "damage_flow_kind": DisputeCase.DamageFlowKind.GENERIC,
            "description": "Expired window",
        },
        format="json",
    )

    assert resp.status_code == 400
    assert "Dispute window expired" in "".join(resp.json().get("non_field_errors", []))


def test_completed_booking_safety_allows_after_window(api_client, booking_factory, renter_user):
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
            "category": DisputeCase.Category.SAFETY_OR_FRAUD,
            "damage_flow_kind": DisputeCase.DamageFlowKind.GENERIC,
            "description": "Safety issue",
        },
        format="json",
    )

    assert resp.status_code == 201
    dispute = DisputeCase.objects.get(id=resp.json()["id"])
    assert dispute.status in {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
    }


def test_renter_broke_during_use_forces_damage_and_locks_deposit(
    api_client, booking_factory, renter_user
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        deposit_hold_id="hold_123",
        deposit_locked=False,
        dispute_window_expires_at=timezone.now() + timedelta(hours=2),
    )
    api_client.force_authenticate(renter_user)

    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.MISSING_ITEM,
            "damage_flow_kind": DisputeCase.DamageFlowKind.BROKE_DURING_USE,
            "description": "Broke during use",
        },
        format="json",
    )

    assert resp.status_code == 201
    dispute = DisputeCase.objects.get(id=resp.json()["id"])
    booking.refresh_from_db()

    assert dispute.damage_flow_kind == DisputeCase.DamageFlowKind.BROKE_DURING_USE
    assert dispute.category == DisputeCase.Category.DAMAGE
    assert dispute.deposit_locked is True
    assert booking.deposit_locked is True
    assert booking.is_disputed is True


def test_owner_broke_during_use_normalized_to_generic(api_client, booking_factory, owner_user):
    today = timezone.localdate()
    booking = booking_factory(
        owner=owner_user,
        renter=owner_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        dispute_window_expires_at=timezone.now() + timedelta(hours=2),
    )

    api_client.force_authenticate(owner_user)
    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "damage_flow_kind": DisputeCase.DamageFlowKind.BROKE_DURING_USE,
            "description": "Owner filed",
        },
        format="json",
    )

    assert resp.status_code == 201
    dispute = DisputeCase.objects.get(id=resp.json()["id"])
    assert dispute.damage_flow_kind == DisputeCase.DamageFlowKind.GENERIC
    assert dispute.opened_by_role == DisputeCase.OpenedByRole.OWNER


def test_evidence_complete_triggers_intake_update(
    api_client, booking_factory, renter_user, monkeypatch
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        dispute_window_expires_at=timezone.now() + timedelta(hours=2),
    )
    api_client.force_authenticate(renter_user)

    create_resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "Need evidence",
        },
        format="json",
    )
    assert create_resp.status_code == 201
    dispute_id = create_resp.json()["id"]

    calls = {"intake": []}

    def fake_update(dispute_pk: int):
        calls["intake"].append(dispute_pk)
        return None

    def fake_delay(**kwargs):
        return None

    monkeypatch.setattr("disputes.api.update_dispute_intake_status", fake_update)
    monkeypatch.setattr("disputes.api.scan_and_finalize_dispute_evidence.delay", fake_delay)

    resp = api_client.post(
        f"/api/disputes/{dispute_id}/evidence/complete/",
        {
            "key": "evidence/key",
            "etag": '"etag123"',
            "size": 123,
            "filename": "proof.jpg",
            "content_type": "image/jpeg",
            "kind": DisputeEvidence.Kind.PHOTO,
        },
        format="json",
    )

    assert resp.status_code == 202
    assert calls["intake"] == [dispute_id]


def test_evidence_complete_skips_intake_update_when_not_missing(
    api_client, booking_factory, renter_user, monkeypatch
):
    today = timezone.localdate()
    booking = booking_factory(
        renter=renter_user,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=Booking.Status.PAID,
        dispute_window_expires_at=timezone.now() + timedelta(hours=2),
    )
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="In review",
        status=DisputeCase.Status.UNDER_REVIEW,
        filed_at=timezone.now(),
    )
    api_client.force_authenticate(renter_user)

    calls = {"intake": []}

    def fake_update(dispute_pk: int):
        calls["intake"].append(dispute_pk)
        return None

    def fake_delay(**kwargs):
        return None

    monkeypatch.setattr("disputes.api.update_dispute_intake_status", fake_update)
    monkeypatch.setattr("disputes.api.scan_and_finalize_dispute_evidence.delay", fake_delay)

    resp = api_client.post(
        f"/api/disputes/{dispute.id}/evidence/complete/",
        {
            "key": "evidence/key",
            "etag": '"etag123"',
            "size": 123,
            "filename": "proof.jpg",
            "content_type": "image/jpeg",
            "kind": DisputeEvidence.Kind.PHOTO,
        },
        format="json",
    )

    assert resp.status_code == 202
    assert calls["intake"] == []
