"""Tests for intake evidence evaluation and status transitions."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking, BookingPhoto
from disputes.intake import update_dispute_intake_status
from disputes.models import DisputeCase, DisputeEvidence

pytestmark = pytest.mark.django_db


def _create_dispute(
    *,
    booking: Booking,
    user,
    category: str,
    damage_flow_kind: str,
    filed_at,
) -> DisputeCase:
    return DisputeCase.objects.create(
        booking=booking,
        opened_by=user,
        opened_by_role=(
            DisputeCase.OpenedByRole.RENTER
            if booking.renter_id == user.id
            else DisputeCase.OpenedByRole.OWNER
        ),
        category=category,
        damage_flow_kind=damage_flow_kind,
        description="test",
        status=DisputeCase.Status.OPEN,
        filed_at=filed_at,
    )


def test_broke_during_use_requires_minimum_evidence(booking_factory, renter_user, monkeypatch):
    now = timezone.now()
    booking = booking_factory(
        renter=renter_user,
        start_date=now.date(),
        end_date=now.date() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    dispute = _create_dispute(
        booking=booking,
        user=renter_user,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.BROKE_DURING_USE,
        filed_at=now,
    )

    email_calls: list[int] = []

    def fake_email(delay_id):
        email_calls.append(delay_id)

    monkeypatch.setattr(
        "disputes.intake.notification_tasks.send_dispute_missing_evidence_email.delay",
        fake_email,
    )
    events: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(
        "disputes.intake.push_event",
        lambda user_id, event_type, payload: events.append((user_id, event_type, payload)),
    )

    updated = update_dispute_intake_status(dispute.id)
    assert updated is not None
    updated.refresh_from_db()
    assert updated.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE
    assert updated.rebuttal_due_at == dispute.filed_at + timedelta(hours=24)
    assert email_calls == [dispute.id]
    assert events == []


def test_broke_during_use_with_video_moves_to_awaiting(
    booking_factory, renter_user, owner_user, monkeypatch
):
    base_now = timezone.now()
    monkeypatch.setattr("disputes.intake.timezone.now", lambda: base_now)
    booking = booking_factory(
        renter=renter_user,
        owner=owner_user,
        start_date=base_now.date(),
        end_date=base_now.date() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    BookingPhoto.objects.create(
        booking=booking,
        uploaded_by=renter_user,
        role=BookingPhoto.Role.BEFORE,
        s3_key="before",
        url="",
        filename="before.jpg",
        content_type="image/jpeg",
        size=123,
        etag="etag",
        av_status=BookingPhoto.AVStatus.CLEAN,
    )
    dispute = _create_dispute(
        booking=booking,
        user=renter_user,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.BROKE_DURING_USE,
        filed_at=base_now - timedelta(hours=1),
    )
    DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=renter_user,
        kind=DisputeEvidence.Kind.VIDEO,
        s3_key="vid",
        av_status=DisputeEvidence.AVStatus.CLEAN,
    )

    email_calls: list[int] = []
    monkeypatch.setattr(
        "disputes.intake.notification_tasks.send_dispute_missing_evidence_email.delay",
        lambda dispute_id: email_calls.append(dispute_id),
    )
    events: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(
        "disputes.intake.push_event",
        lambda user_id, event_type, payload: events.append((user_id, event_type, payload)),
    )

    updated = update_dispute_intake_status(dispute.id)
    assert updated is not None
    updated.refresh_from_db()
    assert updated.status == DisputeCase.Status.AWAITING_REBUTTAL
    assert updated.rebuttal_due_at == base_now + timedelta(hours=24)
    assert email_calls == []
    assert events == [
        (
            booking.owner_id,
            "dispute:opened",
            {
                "dispute_id": dispute.id,
                "booking_id": booking.id,
                "status": DisputeCase.Status.AWAITING_REBUTTAL,
            },
        ),
        (
            booking.renter_id,
            "dispute:opened",
            {
                "dispute_id": dispute.id,
                "booking_id": booking.id,
                "status": DisputeCase.Status.AWAITING_REBUTTAL,
            },
        ),
    ]


def test_damage_requires_booking_photos_for_minimum(booking_factory, renter_user, monkeypatch):
    now = timezone.now()
    monkeypatch.setattr("disputes.intake.timezone.now", lambda: now)
    booking = booking_factory(
        renter=renter_user,
        start_date=now.date(),
        end_date=now.date() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    dispute = _create_dispute(
        booking=booking,
        user=renter_user,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        filed_at=now - timedelta(hours=2),
    )
    DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=renter_user,
        kind=DisputeEvidence.Kind.PHOTO,
        s3_key="photo1",
        av_status=DisputeEvidence.AVStatus.CLEAN,
    )

    email_calls: list[int] = []
    monkeypatch.setattr(
        "disputes.intake.notification_tasks.send_dispute_missing_evidence_email.delay",
        lambda dispute_id: email_calls.append(dispute_id),
    )
    events: list = []
    monkeypatch.setattr("disputes.intake.push_event", lambda *args, **kwargs: events.append(args))

    updated = update_dispute_intake_status(dispute.id)
    assert updated is not None
    updated.refresh_from_db()
    assert updated.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE
    assert updated.rebuttal_due_at == dispute.filed_at + timedelta(hours=24)
    assert email_calls == [dispute.id]
    assert events == []


def test_damage_with_booking_photos_and_evidence_moves_to_awaiting(
    booking_factory, renter_user, owner_user, monkeypatch
):
    base_now = timezone.now()
    monkeypatch.setattr("disputes.intake.timezone.now", lambda: base_now)
    booking = booking_factory(
        renter=renter_user,
        owner=owner_user,
        start_date=base_now.date(),
        end_date=base_now.date() + timedelta(days=1),
        status=Booking.Status.PAID,
    )
    dispute = _create_dispute(
        booking=booking,
        user=renter_user,
        category=DisputeCase.Category.MISSING_ITEM,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        filed_at=base_now,
    )
    BookingPhoto.objects.create(
        booking=booking,
        uploaded_by=renter_user,
        role=BookingPhoto.Role.BEFORE,
        s3_key="before",
        url="",
        filename="before.jpg",
        content_type="image/jpeg",
        size=123,
        etag="etag",
        av_status=BookingPhoto.AVStatus.CLEAN,
    )
    DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=renter_user,
        kind=DisputeEvidence.Kind.PHOTO,
        s3_key="e1",
        av_status=DisputeEvidence.AVStatus.CLEAN,
    )

    email_calls: list[int] = []
    monkeypatch.setattr(
        "disputes.intake.notification_tasks.send_dispute_missing_evidence_email.delay",
        lambda dispute_id: email_calls.append(dispute_id),
    )
    events: list[tuple[int, str, dict]] = []
    monkeypatch.setattr(
        "disputes.intake.push_event",
        lambda user_id, event_type, payload: events.append((user_id, event_type, payload)),
    )

    updated = update_dispute_intake_status(dispute.id)
    assert updated is not None
    updated.refresh_from_db()
    assert updated.status == DisputeCase.Status.AWAITING_REBUTTAL
    assert updated.rebuttal_due_at == base_now + timedelta(hours=24)
    assert email_calls == []
    assert events == [
        (
            booking.owner_id,
            "dispute:opened",
            {
                "dispute_id": dispute.id,
                "booking_id": booking.id,
                "status": DisputeCase.Status.AWAITING_REBUTTAL,
            },
        ),
        (
            booking.renter_id,
            "dispute:opened",
            {
                "dispute_id": dispute.id,
                "booking_id": booking.id,
                "status": DisputeCase.Status.AWAITING_REBUTTAL,
            },
        ),
    ]
