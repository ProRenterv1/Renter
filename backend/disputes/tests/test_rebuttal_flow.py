from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking
from disputes.models import DisputeCase, DisputeEvidence, DisputeMessage
from disputes.tasks import (
    auto_flag_unanswered_rebuttals,
    get_counterparty_user_id,
    start_rebuttal_window,
)

pytestmark = pytest.mark.django_db


def _create_dispute(booking, user, *, status=DisputeCase.Status.OPEN, filed_at=None) -> DisputeCase:
    return DisputeCase.objects.create(
        booking=booking,
        opened_by=user,
        opened_by_role=(
            DisputeCase.OpenedByRole.RENTER
            if booking.renter_id == user.id
            else DisputeCase.OpenedByRole.OWNER
        ),
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="test dispute",
        status=status,
        filed_at=filed_at or timezone.now(),
    )


def _booking_with_dates(booking_factory, *, renter, owner=None, status=Booking.Status.PAID):
    today = timezone.localdate()
    return booking_factory(
        renter=renter,
        owner=owner,
        start_date=today,
        end_date=today + timedelta(days=1),
        status=status,
    )


def test_get_counterparty_user_id_owner_vs_renter(booking_factory, renter_user, owner_user):
    booking = _booking_with_dates(booking_factory, owner=owner_user, renter=renter_user)
    renter_filed = _create_dispute(booking, renter_user)
    owner_filed = _create_dispute(booking, owner_user)

    assert get_counterparty_user_id(renter_filed) == owner_user.id
    assert get_counterparty_user_id(owner_filed) == renter_user.id


def test_start_rebuttal_window_sets_due_and_notifies(
    monkeypatch, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(booking_factory, owner=owner_user, renter=renter_user)
    dispute = _create_dispute(booking, renter_user, status=DisputeCase.Status.OPEN)

    email_calls: list[tuple[int, int]] = []
    sms_calls: list[tuple[int, int]] = []

    monkeypatch.setattr(
        "disputes.tasks.notification_tasks.send_dispute_rebuttal_started_email.delay",
        lambda dispute_id, recipient_id: email_calls.append((dispute_id, recipient_id)),
    )
    monkeypatch.setattr(
        "disputes.tasks.notification_tasks.send_dispute_rebuttal_started_sms.delay",
        lambda dispute_id, recipient_id: sms_calls.append((dispute_id, recipient_id)),
    )

    base_now = timezone.now()
    updated = start_rebuttal_window(dispute.id)
    assert updated == 1

    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.AWAITING_REBUTTAL
    assert dispute.auto_rebuttal_timeout is False
    assert dispute.rebuttal_due_at is not None
    delta = dispute.rebuttal_due_at - base_now
    assert timedelta(hours=23, minutes=50) <= delta <= timedelta(hours=24, minutes=10)
    assert email_calls == [(dispute.id, owner_user.id)]
    assert sms_calls == [(dispute.id, owner_user.id)]


def test_auto_flag_unanswered_rebuttals_marks_under_review(
    monkeypatch, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(booking_factory, owner=owner_user, renter=renter_user)
    due_at = timezone.now() - timedelta(hours=1)
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="needs rebuttal",
        status=DisputeCase.Status.AWAITING_REBUTTAL,
        rebuttal_due_at=due_at,
        filed_at=timezone.now() - timedelta(hours=2),
    )

    ended_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "disputes.tasks.notification_tasks.send_dispute_rebuttal_ended_email.delay",
        lambda dispute_id, user_id: ended_calls.append((dispute_id, user_id)),
    )

    updated = auto_flag_unanswered_rebuttals()
    assert updated == 1

    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.UNDER_REVIEW
    assert dispute.auto_rebuttal_timeout is True
    assert dispute.review_started_at is not None
    assert set(ended_calls) == {(dispute.id, booking.owner_id), (dispute.id, booking.renter_id)}


def test_auto_flag_skips_when_counterparty_messaged(
    monkeypatch, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(booking_factory, owner=owner_user, renter=renter_user)
    due_at = timezone.now() - timedelta(minutes=30)
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="answered",
        status=DisputeCase.Status.AWAITING_REBUTTAL,
        rebuttal_due_at=due_at,
    )
    window_start = due_at - timedelta(hours=24)
    DisputeMessage.objects.create(
        dispute=dispute,
        author=owner_user,
        role=DisputeMessage.Role.OWNER,
        text="reply",
        created_at=window_start + timedelta(minutes=5),
    )

    ended_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "disputes.tasks.notification_tasks.send_dispute_rebuttal_ended_email.delay",
        lambda dispute_id, user_id: ended_calls.append((dispute_id, user_id)),
    )

    updated = auto_flag_unanswered_rebuttals()
    assert updated == 0

    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.AWAITING_REBUTTAL
    assert dispute.auto_rebuttal_timeout is False
    assert ended_calls == []


def test_auto_flag_skips_when_counterparty_uploaded_evidence(
    monkeypatch, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(booking_factory, owner=owner_user, renter=renter_user)
    due_at = timezone.now() - timedelta(minutes=45)
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="evidence provided",
        status=DisputeCase.Status.AWAITING_REBUTTAL,
        rebuttal_due_at=due_at,
    )
    window_start = due_at - timedelta(hours=24)
    DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=owner_user,
        kind=DisputeEvidence.Kind.PHOTO,
        s3_key="evidence/key",
        av_status=DisputeEvidence.AVStatus.CLEAN,
        created_at=window_start + timedelta(minutes=10),
    )

    ended_calls: list[tuple[int, int]] = []
    monkeypatch.setattr(
        "disputes.tasks.notification_tasks.send_dispute_rebuttal_ended_email.delay",
        lambda dispute_id, user_id: ended_calls.append((dispute_id, user_id)),
    )

    updated = auto_flag_unanswered_rebuttals()
    assert updated == 0

    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.AWAITING_REBUTTAL
    assert dispute.auto_rebuttal_timeout is False
    assert ended_calls == []


def test_auto_resolve_pickup_no_show_refunds_and_cancels(
    monkeypatch, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(
        booking_factory,
        renter=renter_user,
        owner=owner_user,
        status=Booking.Status.PAID,
    )
    booking.deposit_hold_id = "pi_deposit_hold"
    booking.charge_payment_intent_id = "pi_charge"
    booking.totals = {
        "rental_subtotal": "100.00",
        "renter_fee_total": "10.00",
        "damage_deposit": "50.00",
        "total_charge": "160.00",
    }
    booking.save(
        update_fields=[
            "deposit_hold_id",
            "charge_payment_intent_id",
            "totals",
            "updated_at",
        ]
    )

    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.PICKUP_NO_SHOW,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="owner didn't show",
        status=DisputeCase.Status.AWAITING_REBUTTAL,
        rebuttal_due_at=timezone.now() - timedelta(minutes=10),
        filed_at=timezone.now() - timedelta(hours=1),
    )
    DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=renter_user,
        kind=DisputeEvidence.Kind.PHOTO,
        s3_key="proof",
        av_status=DisputeEvidence.AVStatus.CLEAN,
    )

    called = {"refund": None, "release": 0}

    def fake_refund(booking_arg, amount_cents):
        called["refund"] = amount_cents
        return "re_test"

    def fake_release(booking_arg):
        called["release"] += 1
        return True

    monkeypatch.setattr("disputes.tasks.settlement.refund_booking_charge", fake_refund)
    monkeypatch.setattr("disputes.tasks.settlement.release_deposit_hold_if_needed", fake_release)

    updated = auto_flag_unanswered_rebuttals()
    assert updated == 1

    dispute.refresh_from_db()
    booking.refresh_from_db()
    assert dispute.status == DisputeCase.Status.RESOLVED_RENTER
    assert dispute.refund_amount_cents == 11000
    assert dispute.resolved_at is not None
    assert dispute.auto_rebuttal_timeout is True
    assert "Auto-resolved" in (dispute.decision_notes or "")
    assert booking.status == Booking.Status.CANCELED
    assert booking.canceled_by == Booking.CanceledBy.NO_SHOW
    assert booking.canceled_reason == "owner_no_show"
    assert booking.auto_canceled is True
    assert called["refund"] == 11000
    assert called["release"] == 1


def test_post_message_endpoint_sets_role_and_author(
    api_client, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(
        booking_factory, renter=renter_user, owner=owner_user, status=Booking.Status.PAID
    )
    api_client.force_authenticate(renter_user)
    create_resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "need response",
        },
        format="json",
    )
    assert create_resp.status_code == 201
    dispute_id = create_resp.json()["id"]

    resp = api_client.post(
        f"/api/disputes/{dispute_id}/messages/",
        {"text": "My response"},
        format="json",
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["role"] == DisputeMessage.Role.RENTER
    assert data["dispute"] == dispute_id
    assert data["author"] == renter_user.id


def test_unrelated_user_cannot_post_message(
    api_client, booking_factory, renter_user, owner_user, other_user
):
    booking = _booking_with_dates(
        booking_factory, renter=renter_user, owner=owner_user, status=Booking.Status.PAID
    )
    api_client.force_authenticate(renter_user)
    dispute_resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "test",
        },
        format="json",
    )
    assert dispute_resp.status_code == 201
    dispute_id = dispute_resp.json()["id"]

    api_client.force_authenticate(other_user)
    resp = api_client.post(
        f"/api/disputes/{dispute_id}/messages/",
        {"text": "not allowed"},
        format="json",
    )
    assert resp.status_code == 403


def test_evidence_presign_and_complete_enqueue_av(
    api_client, booking_factory, renter_user, monkeypatch
):
    booking = _booking_with_dates(booking_factory, renter=renter_user, status=Booking.Status.PAID)
    api_client.force_authenticate(renter_user)
    dispute_resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "description": "evidence flow",
        },
        format="json",
    )
    assert dispute_resp.status_code == 201
    dispute_id = dispute_resp.json()["id"]

    def fake_booking_key(booking_id, user_id, filename):
        return f"disputes/{dispute_id}/{booking_id}/{user_id}/{filename}"

    monkeypatch.setattr(
        "disputes.api.booking_object_key",
        fake_booking_key,
    )
    presign_resp = api_client.post(
        f"/api/disputes/{dispute_id}/evidence/presign/",
        {"filename": "proof.jpg", "content_type": "image/jpeg", "size": 123},
        format="json",
    )
    assert presign_resp.status_code == 200
    assert "upload_url" in presign_resp.json()
    assert "key" in presign_resp.json()
    assert str(dispute_id) in presign_resp.json()["key"]

    av_calls: list[dict] = []

    def fake_delay(**kwargs):
        av_calls.append(kwargs)

    monkeypatch.setattr("disputes.api.scan_and_finalize_dispute_evidence.delay", fake_delay)

    complete_resp = api_client.post(
        f"/api/disputes/{dispute_id}/evidence/complete/",
        {
            "key": presign_resp.json()["key"],
            "etag": '"etag123"',
            "size": 123,
            "filename": "proof.jpg",
            "content_type": "image/jpeg",
            "kind": DisputeEvidence.Kind.PHOTO,
        },
        format="json",
    )
    assert complete_resp.status_code == 202
    evidence = DisputeEvidence.objects.get(dispute_id=dispute_id, uploaded_by=renter_user)
    assert evidence.filename == "proof.jpg"
    assert av_calls and av_calls[0]["dispute_id"] == dispute_id


def test_dispute_detail_includes_rebuttal_fields(
    api_client, booking_factory, renter_user, owner_user
):
    booking = _booking_with_dates(
        booking_factory, renter=renter_user, owner=owner_user, status=Booking.Status.PAID
    )
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        damage_flow_kind=DisputeCase.DamageFlowKind.GENERIC,
        description="detail check",
        status=DisputeCase.Status.AWAITING_REBUTTAL,
        filed_at=timezone.now(),
        rebuttal_due_at=timezone.now() + timedelta(hours=12),
        auto_rebuttal_timeout=False,
    )
    DisputeMessage.objects.create(
        dispute=dispute,
        author=renter_user,
        role=DisputeMessage.Role.RENTER,
        text="hello",
    )
    DisputeEvidence.objects.create(
        dispute=dispute,
        uploaded_by=renter_user,
        kind=DisputeEvidence.Kind.PHOTO,
        s3_key="k",
        filename="f.jpg",
        av_status=DisputeEvidence.AVStatus.PENDING,
    )

    api_client.force_authenticate(owner_user)
    resp = api_client.get(f"/api/disputes/{dispute.id}/")
    assert resp.status_code == 200
    data = resp.json()
    for field in ["status", "rebuttal_due_at", "auto_rebuttal_timeout"]:
        assert field in data
    assert isinstance(data.get("messages"), list)
    assert isinstance(data.get("evidence"), list)
