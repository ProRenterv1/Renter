from __future__ import annotations

import logging
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Optional

from celery import shared_task
from django.apps import apps
from django.db import transaction
from django.utils import timezone

from bookings.domain import mark_canceled
from bookings.models import Booking
from core.settings_resolver import get_int
from notifications import tasks as notification_tasks
from payments.stripe_api import StripePaymentError

from .models import DisputeCase, DisputeEvidence, DisputeMessage
from .services import settlement

logger = logging.getLogger(__name__)

_DISPUTE_WRITE_LOCKED_STATUSES = {
    DisputeCase.Status.RESOLVED_RENTER,
    DisputeCase.Status.RESOLVED_OWNER,
    DisputeCase.Status.RESOLVED_PARTIAL,
    DisputeCase.Status.CLOSED_AUTO,
}


def _parse_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _booking_charge_amount_cents(booking: Booking) -> int:
    totals = booking.totals or {}
    total_charge_raw = totals.get("total_charge")
    damage_deposit_raw = totals.get("damage_deposit")
    if total_charge_raw is not None:
        total_charge = _parse_decimal(total_charge_raw)
        damage_deposit = (
            _parse_decimal(damage_deposit_raw) if damage_deposit_raw is not None else Decimal("0")
        )
        charge_amount = total_charge - damage_deposit
    else:
        rental_subtotal = _parse_decimal(totals.get("rental_subtotal"))
        renter_fee_raw = totals.get("renter_fee_total")
        if renter_fee_raw is None:
            renter_fee_raw = totals.get("renter_fee")
        if renter_fee_raw is None:
            renter_fee_raw = totals.get("service_fee")
        renter_fee = _parse_decimal(renter_fee_raw)
        charge_amount = rental_subtotal + renter_fee

    if charge_amount <= Decimal("0"):
        return 0
    cents = (charge_amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


def _filer_has_evidence(dispute: DisputeCase) -> bool:
    if not dispute.opened_by_id:
        return False
    return (
        DisputeEvidence.objects.filter(
            dispute_id=dispute.id,
            uploaded_by_id=dispute.opened_by_id,
        )
        .exclude(
            av_status__in=[
                DisputeEvidence.AVStatus.INFECTED,
                DisputeEvidence.AVStatus.FAILED,
            ]
        )
        .exists()
    )


def _finalize_booking_flags(booking: Booking, dispute_id: int) -> None:
    active_statuses = {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
        DisputeCase.Status.UNDER_REVIEW,
    }
    other_active = (
        DisputeCase.objects.filter(booking=booking, status__in=active_statuses)
        .exclude(pk=dispute_id)
        .exists()
    )
    if other_active:
        return
    booking.is_disputed = False
    booking.deposit_locked = False
    booking.save(update_fields=["is_disputed", "deposit_locked", "updated_at"])


def get_counterparty_user_id(dispute: DisputeCase) -> Optional[int]:
    """Return the user id for the non-filing party on the booking."""
    booking = getattr(dispute, "booking", None)
    if not booking:
        return None
    if dispute.opened_by_role == DisputeCase.OpenedByRole.RENTER:
        return booking.owner_id
    if dispute.opened_by_role == DisputeCase.OpenedByRole.OWNER:
        return booking.renter_id
    return None


def _log_booking_event(booking_id: int | None, type_value: str, payload: dict) -> None:
    if not booking_id:
        return
    try:
        BookingEvent = apps.get_model("operator_bookings", "BookingEvent")
        Booking = apps.get_model("bookings", "Booking")
        booking = Booking.objects.filter(pk=booking_id).first() if Booking else None
        if booking and BookingEvent:
            BookingEvent.objects.create(booking=booking, type=type_value, payload=payload)
    except Exception:
        logger.exception(
            "disputes: failed to log booking event",
            extra={"booking_id": booking_id, "type": type_value},
        )


def _auto_resolve_pickup_no_show(dispute: DisputeCase, now) -> bool:
    booking = getattr(dispute, "booking", None)
    if not booking:
        return False
    if not _filer_has_evidence(dispute):
        return False

    refund_amount_cents = _booking_charge_amount_cents(booking)
    if refund_amount_cents <= 0:
        logger.info(
            "disputes.auto_resolve_no_show: missing refund amount for booking %s",
            booking.id,
        )
        return False

    try:
        settlement.refund_booking_charge(booking, refund_amount_cents)
    except StripePaymentError:
        logger.warning(
            "disputes.auto_resolve_no_show: refund failed for booking %s",
            booking.id,
            exc_info=True,
        )
        return False

    try:
        settlement.release_deposit_hold_if_needed(booking)
    except StripePaymentError as exc:
        logger.info(
            "disputes.auto_resolve_no_show: deposit release failed for booking %s: %s",
            booking.id,
            exc,
            exc_info=True,
        )

    if dispute.opened_by_role == DisputeCase.OpenedByRole.RENTER:
        resolved_status = DisputeCase.Status.RESOLVED_RENTER
        cancel_reason = "owner_no_show"
    else:
        resolved_status = DisputeCase.Status.RESOLVED_OWNER
        cancel_reason = "renter_no_show"

    decision_note = "Auto-resolved: pickup no-show (no rebuttal received)."

    try:
        with transaction.atomic():
            locked = (
                DisputeCase.objects.select_for_update().select_related("booking").get(pk=dispute.id)
            )
            if locked.status != DisputeCase.Status.AWAITING_REBUTTAL:
                return False

            booking_locked = locked.booking
            if booking_locked and booking_locked.status in {
                Booking.Status.REQUESTED,
                Booking.Status.CONFIRMED,
                Booking.Status.PAID,
            }:
                mark_canceled(
                    booking_locked,
                    actor=Booking.CanceledBy.NO_SHOW,
                    auto=True,
                    reason=cancel_reason,
                )
                booking_locked.save(
                    update_fields=[
                        "status",
                        "canceled_by",
                        "canceled_reason",
                        "auto_canceled",
                        "updated_at",
                    ]
                )

            locked.status = resolved_status
            locked.refund_amount_cents = refund_amount_cents
            locked.auto_rebuttal_timeout = True
            locked.resolved_at = now
            existing_notes = (locked.decision_notes or "").strip()
            locked.decision_notes = f"{existing_notes} {decision_note}".strip()
            locked.save(
                update_fields=[
                    "status",
                    "refund_amount_cents",
                    "auto_rebuttal_timeout",
                    "resolved_at",
                    "decision_notes",
                    "updated_at",
                ]
            )

            if booking_locked:
                _finalize_booking_flags(booking_locked, locked.id)
    except Exception:
        logger.exception(
            "disputes.auto_resolve_no_show: failed to update dispute %s",
            dispute.id,
        )
        return False

    _log_booking_event(
        getattr(booking, "id", None),
        "dispute_resolved",
        {
            "dispute_id": dispute.id,
            "decision": resolved_status,
            "refund_amount_cents": refund_amount_cents,
            "reason": cancel_reason,
        },
    )

    try:
        notification_tasks.notify_dispute_resolved(dispute.id)
    except Exception:
        logger.info(
            "disputes.auto_resolve_no_show: failed to notify resolution for dispute %s",
            dispute.id,
            exc_info=True,
        )

    return True


@shared_task(name="disputes.start_rebuttal_window")
def start_rebuttal_window(dispute_id: int) -> int:
    """Move a dispute into rebuttal, set deadline, and notify the counterparty."""
    dispute: Optional[DisputeCase] = None
    updated = 0
    try:
        with transaction.atomic():
            try:
                dispute = (
                    DisputeCase.objects.select_for_update()
                    .select_related("booking")
                    .get(pk=dispute_id)
                )
            except DisputeCase.DoesNotExist:
                logger.warning("disputes.start_rebuttal_window: dispute %s not found", dispute_id)
                return 0

            if dispute.status in _DISPUTE_WRITE_LOCKED_STATUSES:
                return 0

            now = timezone.now()
            update_fields: list[str] = []

            if dispute.status != DisputeCase.Status.AWAITING_REBUTTAL:
                dispute.status = DisputeCase.Status.AWAITING_REBUTTAL
                update_fields.append("status")

            new_rebuttal_due_at = dispute.rebuttal_due_at
            if new_rebuttal_due_at is None or new_rebuttal_due_at <= now:
                rebuttal_window_hours = get_int("DISPUTE_REBUTTAL_WINDOW_HOURS", 24)
                if dispute.category == DisputeCase.Category.PICKUP_NO_SHOW:
                    rebuttal_window_hours = max(get_int("DISPUTE_NO_SHOW_REBUTTAL_HOURS", 2), 1)
                new_rebuttal_due_at = now + timedelta(hours=rebuttal_window_hours)
            if dispute.rebuttal_due_at != new_rebuttal_due_at:
                dispute.rebuttal_due_at = new_rebuttal_due_at
                update_fields.append("rebuttal_due_at")

            if dispute.auto_rebuttal_timeout:
                dispute.auto_rebuttal_timeout = False
                update_fields.append("auto_rebuttal_timeout")

            if update_fields:
                update_fields.append("updated_at")
                dispute.save(update_fields=update_fields)
                updated = 1
    except Exception:
        logger.exception("disputes.start_rebuttal_window: failed for dispute %s", dispute_id)
        return 0

    if not dispute:
        return updated

    counterparty_id = get_counterparty_user_id(dispute)
    if not counterparty_id:
        return updated

    try:
        notification_tasks.send_dispute_rebuttal_started_email.delay(dispute.id, counterparty_id)
    except Exception:
        logger.info(
            "disputes.start_rebuttal_window: failed to enqueue rebuttal email",
            extra={"dispute_id": dispute.id, "counterparty_id": counterparty_id},
            exc_info=True,
        )

    try:
        notification_tasks.send_dispute_rebuttal_started_sms.delay(dispute.id, counterparty_id)
    except Exception:
        logger.info(
            "disputes.start_rebuttal_window: failed to enqueue rebuttal SMS",
            extra={"dispute_id": dispute.id, "counterparty_id": counterparty_id},
            exc_info=True,
        )

    return updated


@shared_task(name="disputes.auto_flag_unanswered_rebuttals")
def auto_flag_unanswered_rebuttals() -> int:
    """Auto-flag disputes with no rebuttal response after the 24h window."""
    now = timezone.now()
    candidates = (
        DisputeCase.objects.filter(
            status=DisputeCase.Status.AWAITING_REBUTTAL,
            rebuttal_due_at__isnull=False,
            rebuttal_due_at__lte=now,
        )
        .select_related("booking")
        .iterator()
    )

    updated_count = 0

    rebuttal_window_hours = get_int("DISPUTE_REBUTTAL_WINDOW_HOURS", 24)
    no_show_window_hours = max(get_int("DISPUTE_NO_SHOW_REBUTTAL_HOURS", 2), 1)
    for dispute in candidates:
        counterparty_id = get_counterparty_user_id(dispute)
        if not counterparty_id or not dispute.rebuttal_due_at:
            continue

        window_hours = (
            no_show_window_hours
            if dispute.category == DisputeCase.Category.PICKUP_NO_SHOW
            else rebuttal_window_hours
        )
        window_start = dispute.rebuttal_due_at - timedelta(hours=window_hours)

        has_message = DisputeMessage.objects.filter(
            dispute_id=dispute.id,
            author_id=counterparty_id,
            created_at__gte=window_start,
        ).exists()
        if has_message:
            continue

        has_evidence = DisputeEvidence.objects.filter(
            dispute_id=dispute.id,
            uploaded_by_id=counterparty_id,
            created_at__gte=window_start,
        ).exists()
        if has_evidence:
            continue

        if dispute.category == DisputeCase.Category.PICKUP_NO_SHOW:
            resolved = _auto_resolve_pickup_no_show(dispute, now)
            if resolved:
                updated_count += 1
                continue

        dispute_to_notify: Optional[DisputeCase] = None
        try:
            with transaction.atomic():
                locked = (
                    DisputeCase.objects.select_for_update()
                    .select_related("booking")
                    .get(pk=dispute.id)
                )
                if locked.status != DisputeCase.Status.AWAITING_REBUTTAL:
                    continue

                update_fields: list[str] = []
                if not locked.auto_rebuttal_timeout:
                    locked.auto_rebuttal_timeout = True
                    update_fields.append("auto_rebuttal_timeout")

                if locked.status != DisputeCase.Status.UNDER_REVIEW:
                    locked.status = DisputeCase.Status.UNDER_REVIEW
                    update_fields.append("status")

                if not locked.review_started_at:
                    locked.review_started_at = now
                    update_fields.append("review_started_at")

                if update_fields:
                    update_fields.append("updated_at")
                    locked.save(update_fields=update_fields)
                    updated_count += 1
                    dispute_to_notify = locked
        except Exception:
            logger.exception(
                "disputes.auto_flag_unanswered_rebuttals: failed processing dispute %s",
                dispute.id,
            )
            continue

        if not dispute_to_notify or not dispute_to_notify.booking:
            continue

        for user_id in (
            dispute_to_notify.booking.owner_id,
            dispute_to_notify.booking.renter_id,
        ):
            if not user_id:
                continue
            try:
                notification_tasks.send_dispute_rebuttal_ended_email.delay(
                    dispute_to_notify.id, user_id
                )
            except Exception:
                logger.info(
                    "disputes.auto_flag_unanswered_rebuttals: failed"
                    " to enqueue rebuttal-ended email",
                    extra={"dispute_id": dispute_to_notify.id, "user_id": user_id},
                    exc_info=True,
                )

    logger.info(
        "disputes.auto_flag_unanswered_rebuttals: updated %s disputes",
        updated_count,
    )
    return updated_count


@shared_task(name="disputes.auto_close_missing_evidence")
def auto_close_missing_evidence() -> int:
    """Auto-close disputes missing evidence after deadline."""
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
        .iterator()
    )
    closed_count = 0
    for dispute in candidates:
        booking = dispute.booking
        try:
            with transaction.atomic():
                locked = (
                    DisputeCase.objects.select_for_update()
                    .select_related("booking")
                    .get(pk=dispute.id)
                )
                if locked.status != DisputeCase.Status.INTAKE_MISSING_EVIDENCE:
                    continue
                locked.status = DisputeCase.Status.CLOSED_AUTO
                locked.resolved_at = now
                locked.decision_notes = "Auto-closed: evidence not provided"
                locked.updated_at = now
                locked.save(update_fields=["status", "resolved_at", "decision_notes", "updated_at"])
                closed_count += 1

                if booking:
                    other_active = DisputeCase.objects.filter(
                        booking=booking, status__in=active_statuses
                    ).exclude(pk=locked.id)
                    if not other_active.exists():
                        booking.deposit_locked = False
                        booking.save(update_fields=["deposit_locked", "updated_at"])
                _log_booking_event(
                    getattr(booking, "id", None),
                    "operator_action",
                    {"action": "dispute_auto_closed_missing_evidence", "dispute_id": locked.id},
                )
        except Exception:
            logger.exception(
                "disputes.auto_close_missing_evidence: failed for dispute %s", dispute.id
            )
            continue
    return closed_count


@shared_task(name="disputes.send_rebuttal_reminders")
def send_rebuttal_reminders() -> int:
    """Send 12h prior reminders for rebuttal deadlines."""
    now = timezone.now()
    upcoming = now + timedelta(hours=12)
    candidates = (
        DisputeCase.objects.filter(
            status=DisputeCase.Status.AWAITING_REBUTTAL,
            rebuttal_due_at__isnull=False,
            rebuttal_due_at__lte=upcoming,
            rebuttal_due_at__gt=now,
        )
        .exclude(category=DisputeCase.Category.PICKUP_NO_SHOW)
        .filter(rebuttal_12h_reminder_sent_at__isnull=True)
        .select_related("booking")
        .iterator()
    )
    sent = 0
    for dispute in candidates:
        counterparty_id = get_counterparty_user_id(dispute)
        if not counterparty_id:
            continue
        try:
            with transaction.atomic():
                locked = (
                    DisputeCase.objects.select_for_update()
                    .select_related("booking")
                    .get(pk=dispute.id)
                )
                if locked.rebuttal_12h_reminder_sent_at:
                    continue
                locked.rebuttal_12h_reminder_sent_at = now
                locked.save(update_fields=["rebuttal_12h_reminder_sent_at", "updated_at"])
                sent += 1
        except Exception:
            logger.exception(
                "disputes.send_rebuttal_reminders: failed locking dispute %s", dispute.id
            )
            continue

        try:
            notification_tasks.send_dispute_rebuttal_reminder_email.delay(
                dispute.id, counterparty_id
            )
        except Exception:
            logger.info(
                "disputes.send_rebuttal_reminders: failed email enqueue",
                extra={"dispute_id": dispute.id, "counterparty_id": counterparty_id},
                exc_info=True,
            )
        try:
            notification_tasks.send_dispute_rebuttal_reminder_sms.delay(dispute.id, counterparty_id)
        except Exception:
            logger.info(
                "disputes.send_rebuttal_reminders: failed sms enqueue",
                extra={"dispute_id": dispute.id, "counterparty_id": counterparty_id},
                exc_info=True,
            )

        _log_booking_event(
            getattr(dispute.booking, "id", None),
            "operator_action",
            {"action": "dispute_rebuttal_reminder", "dispute_id": dispute.id},
        )
    return sent
