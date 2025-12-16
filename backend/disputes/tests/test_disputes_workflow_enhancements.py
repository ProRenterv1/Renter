from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from bookings.models import Booking
from disputes import tasks as dispute_tasks
from disputes.models import DisputeCase
from notifications import tasks as notification_tasks
from notifications.models import NotificationLog
from operator_bookings.models import BookingEvent

pytestmark = pytest.mark.django_db


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_duplicate_dispute_protection(api_client, booking_factory, renter_user):
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID)
    DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="first",
        status=DisputeCase.Status.OPEN,
    )
    api_client.force_authenticate(renter_user)
    resp = api_client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "damage_flow_kind": DisputeCase.DamageFlowKind.GENERIC,
            "description": "dup",
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "active dispute" in "".join(resp.json().get("booking", []))


def test_intake_missing_evidence_sets_deadline_and_notifications(
    monkeypatch, settings, booking_factory, renter_user
):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID)
    client = _auth_client(renter_user)

    # execute reminders synchronously
    monkeypatch.setattr(
        notification_tasks.send_dispute_missing_evidence_email,
        "delay",
        lambda dispute_id: notification_tasks.send_dispute_missing_evidence_email.run(dispute_id),
    )
    monkeypatch.setattr(
        notification_tasks.send_dispute_missing_evidence_sms,
        "delay",
        lambda dispute_id: (
            NotificationLog.objects.create(
                channel=NotificationLog.Channel.SMS,
                type="dispute_missing_evidence",
                status=NotificationLog.Status.SENT,
                booking_id=booking.id,
            ),
            BookingEvent.objects.create(
                booking=booking,
                type=BookingEvent.Type.SMS_SENT,
                payload={"notification_type": "dispute_missing_evidence"},
            ),
        ),
    )

    resp = client.post(
        "/api/disputes/",
        {
            "booking": booking.id,
            "category": DisputeCase.Category.DAMAGE,
            "damage_flow_kind": DisputeCase.DamageFlowKind.GENERIC,
            "description": "need evidence",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.json()
    dispute = DisputeCase.objects.get(id=resp.json()["id"])
    assert dispute.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE
    assert dispute.intake_evidence_due_at is not None
    delta = dispute.intake_evidence_due_at - dispute.filed_at
    assert timedelta(hours=23) < delta < timedelta(hours=25)
    assert NotificationLog.objects.filter(
        booking_id=booking.id, type="dispute_missing_evidence"
    ).exists()


def test_auto_close_missing_evidence_unlocks_when_no_other_active(booking_factory, renter_user):
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID, deposit_locked=True)
    DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="no evidence",
        status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        intake_evidence_due_at=timezone.now() - timedelta(hours=1),
    )
    dispute_tasks.auto_close_missing_evidence.run()
    dispute = DisputeCase.objects.get(booking=booking)
    booking.refresh_from_db()
    assert dispute.status == DisputeCase.Status.CLOSED_AUTO
    assert dispute.resolved_at is not None
    assert "Auto-closed" in (dispute.decision_notes or "")
    assert booking.deposit_locked is False
    assert BookingEvent.objects.filter(
        booking=booking, payload__action="dispute_auto_closed_missing_evidence"
    ).exists()


def test_auto_close_missing_evidence_keeps_deposit_when_other_active(booking_factory, renter_user):
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID, deposit_locked=True)
    DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="active",
        status=DisputeCase.Status.OPEN,
    )
    DisputeCase.objects.create(
        booking=booking,
        opened_by=renter_user,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="no evidence",
        status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        intake_evidence_due_at=timezone.now() - timedelta(hours=1),
    )
    dispute_tasks.auto_close_missing_evidence.run()
    booking.refresh_from_db()
    assert booking.deposit_locked is True


def test_rebuttal_reminder_sent_once(monkeypatch, booking_factory, renter_user, owner_user):
    booking = booking_factory(renter=renter_user, owner=owner_user, status=Booking.Status.PAID)
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=owner_user,
        opened_by_role=DisputeCase.OpenedByRole.OWNER,
        category=DisputeCase.Category.DAMAGE,
        description="pending rebuttal",
        status=DisputeCase.Status.AWAITING_REBUTTAL,
        rebuttal_due_at=timezone.now() + timedelta(hours=6),
    )
    calls = []

    monkeypatch.setattr(
        notification_tasks.send_dispute_rebuttal_reminder_email,
        "delay",
        lambda dispute_id, recipient_id: calls.append(("email", dispute_id, recipient_id)),
    )
    monkeypatch.setattr(
        notification_tasks.send_dispute_rebuttal_reminder_sms,
        "delay",
        lambda dispute_id, recipient_id: calls.append(("sms", dispute_id, recipient_id)),
    )

    sent = dispute_tasks.send_rebuttal_reminders.run()
    assert sent == 1
    dispute.refresh_from_db()
    assert dispute.rebuttal_12h_reminder_sent_at is not None
    assert ("email", dispute.id, renter_user.id) in calls or (
        "email",
        dispute.id,
        owner_user.id,
    ) in calls

    # second run should not resend
    calls.clear()
    sent_again = dispute_tasks.send_rebuttal_reminders.run()
    assert sent_again == 0
    assert calls == []
