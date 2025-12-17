from __future__ import annotations

from datetime import timedelta
from typing import Callable

from django.db import transaction
from django.utils import timezone

from core.settings_resolver import get_int

JobFn = Callable[[dict], dict]


def _get_int_param(params: dict, key: str, default: int, *, min_value: int | None = None) -> int:
    raw = params.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if min_value is not None and value < min_value:
        return default
    return value


def _get_bool_param(params: dict, key: str, default: bool) -> bool:
    raw = params.get(key, default)
    if type(raw) is bool:
        return raw
    return default


def auto_close_missing_evidence_disputes(params: dict) -> dict:
    """
    Auto-close disputes stuck in INTAKE_MISSING_EVIDENCE past intake_evidence_due_at.

    Params:
      - limit: int (default 2000)

    Output:
      - closed_count: int
      - ids: list[int] (max 200)
    """

    from disputes.models import DisputeCase
    from operator_bookings.models import BookingEvent

    limit = _get_int_param(params, "limit", 2000, min_value=1)
    now = timezone.now()

    active_statuses = {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
        DisputeCase.Status.UNDER_REVIEW,
    }

    candidates = (
        DisputeCase.objects.filter(
            status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            intake_evidence_due_at__isnull=False,
            intake_evidence_due_at__lt=now,
        )
        .select_related("booking")
        .order_by("intake_evidence_due_at", "id")[:limit]
    )

    closed_count = 0
    closed_ids: list[int] = []

    for dispute in candidates:
        try:
            with transaction.atomic():
                locked = (
                    DisputeCase.objects.select_for_update()
                    .select_related("booking")
                    .get(pk=dispute.id)
                )
                if locked.status != DisputeCase.Status.INTAKE_MISSING_EVIDENCE:
                    continue
                booking = getattr(locked, "booking", None)

                locked.status = DisputeCase.Status.CLOSED_AUTO
                locked.resolved_at = now
                locked.decision_notes = "Auto-closed: evidence not provided"
                locked.save(update_fields=["status", "resolved_at", "decision_notes", "updated_at"])
                closed_count += 1
                if len(closed_ids) < 200:
                    closed_ids.append(locked.id)

                if booking:
                    other_active = (
                        DisputeCase.objects.filter(booking=booking, status__in=active_statuses)
                        .exclude(pk=locked.id)
                        .exists()
                    )
                    if not other_active and getattr(booking, "deposit_locked", None) is True:
                        booking.deposit_locked = False
                        booking.save(update_fields=["deposit_locked", "updated_at"])

                if booking:
                    try:
                        BookingEvent.objects.create(
                            booking=booking,
                            type=BookingEvent.Type.OPERATOR_ACTION,
                            payload={
                                "action": "dispute_auto_closed_missing_evidence",
                                "dispute_id": locked.id,
                            },
                        )
                    except Exception:
                        pass
        except Exception:
            continue

    return {"closed_count": closed_count, "ids": closed_ids}


def recalc_dispute_window_for_bookings_missing_expires_at(params: dict) -> dict:
    """
    Backfill Booking.dispute_window_expires_at for completed returns.

    Finds bookings where:
      - return_confirmed_at IS NOT NULL
      - dispute_window_expires_at IS NULL

    Computes:
      dispute_window_expires_at = return_confirmed_at + filing_hours

    Params:
      - limit: int (default 5000)
      - dry_run: bool (default True)

    Output:
      - updated_count: int
      - dry_run: bool
      - filing_hours: int
    """

    from bookings.models import Booking

    limit = _get_int_param(params, "limit", 5000, min_value=1)
    dry_run = _get_bool_param(params, "dry_run", True)

    filing_hours = get_int("DISPUTE_FILING_WINDOW_HOURS", 24)
    if filing_hours <= 0:
        filing_hours = 24

    qs = (
        Booking.objects.filter(
            return_confirmed_at__isnull=False, dispute_window_expires_at__isnull=True
        )
        .order_by("return_confirmed_at", "id")
        .only("id", "return_confirmed_at")[:limit]
    )

    updated = 0
    now = timezone.now()
    for booking in qs:
        if dry_run:
            updated += 1
            continue
        anchor = booking.return_confirmed_at
        if not anchor:
            continue
        new_expires = anchor + timedelta(hours=filing_hours)
        updated += Booking.objects.filter(
            pk=booking.id, dispute_window_expires_at__isnull=True
        ).update(dispute_window_expires_at=new_expires, updated_at=now)

    return {"updated_count": updated, "dry_run": dry_run, "filing_hours": filing_hours}


def scan_disputes_stuck_in_stage(params: dict) -> dict:
    """
    Scan for disputes stuck in OPEN/INTAKE/REBUTTAL/REVIEW with stale updated_at.

    Params:
      - stale_hours: int (default 48)
      - limit: int (default 500)

    Output:
      - count: int
      - ids: list[int]
      - oldest_updated_at: ISO string | None
    """

    from disputes.models import DisputeCase

    limit = _get_int_param(params, "limit", 500, min_value=1)
    stale_hours = _get_int_param(params, "stale_hours", 48, min_value=1)
    cutoff = timezone.now() - timedelta(hours=stale_hours)

    stale_statuses = {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
        DisputeCase.Status.UNDER_REVIEW,
    }

    qs = (
        DisputeCase.objects.filter(status__in=stale_statuses, updated_at__lt=cutoff)
        .order_by("updated_at", "id")
        .values_list("id", "updated_at")[:limit]
    )

    ids: list[int] = []
    oldest_updated_at = None
    for dispute_id, updated_at in qs:
        if oldest_updated_at is None and updated_at is not None:
            oldest_updated_at = updated_at.isoformat()
        ids.append(int(dispute_id))

    return {"count": len(ids), "ids": ids, "oldest_updated_at": oldest_updated_at}


JOB_REGISTRY: dict[str, JobFn] = {
    "auto_close_missing_evidence_disputes": auto_close_missing_evidence_disputes,
    "recalc_dispute_window_for_bookings_missing_expires_at": (
        recalc_dispute_window_for_bookings_missing_expires_at
    ),
    "scan_disputes_stuck_in_stage": scan_disputes_stuck_in_stage,
}
