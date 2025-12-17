from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking
from disputes.models import DisputeCase
from operator_settings.jobs import (
    auto_close_missing_evidence_disputes,
    recalc_dispute_window_for_bookings_missing_expires_at,
    scan_disputes_stuck_in_stage,
)
from operator_settings.models import OperatorJobRun
from operator_settings.tasks import operator_run_job

pytestmark = pytest.mark.django_db


def test_auto_close_missing_evidence_disputes_closes_only_eligible(
    booking_factory, renter_user, dispute_factory
):
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID, deposit_locked=True)

    eligible = dispute_factory(
        booking=booking,
        opened_by=renter_user,
        status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        intake_evidence_due_at=timezone.now() - timedelta(hours=1),
    )
    ineligible_future = dispute_factory(
        booking=booking,
        opened_by=renter_user,
        status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        intake_evidence_due_at=timezone.now() + timedelta(hours=1),
    )
    ineligible_status = dispute_factory(
        booking=booking,
        opened_by=renter_user,
        status=DisputeCase.Status.OPEN,
        intake_evidence_due_at=timezone.now() - timedelta(hours=1),
    )

    out = auto_close_missing_evidence_disputes({"limit": 2000})
    assert out["closed_count"] == 1
    assert eligible.id in out["ids"]

    eligible.refresh_from_db()
    ineligible_future.refresh_from_db()
    ineligible_status.refresh_from_db()
    booking.refresh_from_db()

    assert eligible.status == DisputeCase.Status.CLOSED_AUTO
    assert eligible.resolved_at is not None
    assert ineligible_future.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE
    assert ineligible_status.status == DisputeCase.Status.OPEN
    assert booking.deposit_locked is True

    out2 = auto_close_missing_evidence_disputes({"limit": 2000})
    assert out2["closed_count"] == 0


def test_recalc_dispute_window_for_bookings_missing_expires_at_respects_dry_run(
    booking_factory, db_setting_factory
):
    db_setting_factory(key="DISPUTE_FILING_WINDOW_HOURS", value_json=1, value_type="int")
    booking = booking_factory(
        status=Booking.Status.PAID,
        return_confirmed_at=timezone.now(),
        dispute_window_expires_at=None,
    )

    out = recalc_dispute_window_for_bookings_missing_expires_at({"limit": 10, "dry_run": True})
    assert out["dry_run"] is True
    assert out["updated_count"] == 1
    assert out["filing_hours"] == 1
    booking.refresh_from_db()
    assert booking.dispute_window_expires_at is None

    out2 = recalc_dispute_window_for_bookings_missing_expires_at({"limit": 10, "dry_run": False})
    assert out2["dry_run"] is False
    assert out2["updated_count"] == 1
    assert out2["filing_hours"] == 1
    booking.refresh_from_db()
    assert booking.dispute_window_expires_at is not None
    delta = booking.dispute_window_expires_at - booking.return_confirmed_at
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)

    out3 = recalc_dispute_window_for_bookings_missing_expires_at({"limit": 10, "dry_run": False})
    assert out3["updated_count"] == 0


def test_scan_disputes_stuck_in_stage_does_not_mutate(
    booking_factory, renter_user, dispute_factory
):
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID)
    dispute = dispute_factory(
        booking=booking, opened_by=renter_user, status=DisputeCase.Status.OPEN
    )
    DisputeCase.objects.filter(pk=dispute.pk).update(
        updated_at=timezone.now() - timedelta(hours=100)
    )
    dispute.refresh_from_db()
    before_updated_at = dispute.updated_at

    out = scan_disputes_stuck_in_stage({"stale_hours": 48, "limit": 10})
    assert out["count"] >= 1
    assert dispute.id in out["ids"]
    assert out["oldest_updated_at"] is not None

    dispute.refresh_from_db()
    assert dispute.status == DisputeCase.Status.OPEN
    assert dispute.updated_at == before_updated_at


def test_operator_run_job_persists_output_and_status():
    run = OperatorJobRun.objects.create(
        name="scan_disputes_stuck_in_stage",
        params={"stale_hours": 48, "limit": 10},
        status=OperatorJobRun.Status.QUEUED,
    )

    result = operator_run_job(run.id)
    assert result["ok"] is True

    run.refresh_from_db()
    assert run.status == OperatorJobRun.Status.SUCCEEDED
    assert run.finished_at is not None
    assert run.output_json and run.output_json.get("ok") is True


def test_operator_run_job_persists_error_for_unknown_job():
    run = OperatorJobRun.objects.create(
        name="does_not_exist",
        params={},
        status=OperatorJobRun.Status.QUEUED,
    )

    result = operator_run_job(run.id)
    assert result["ok"] is False

    run.refresh_from_db()
    assert run.status == OperatorJobRun.Status.FAILED
    assert run.finished_at is not None
    assert run.output_json and run.output_json.get("ok") is False
    assert run.output_json.get("error", {}).get("type")
