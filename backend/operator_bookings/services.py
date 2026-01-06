import logging
from datetime import date, timedelta
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from bookings.domain import (
    assert_can_cancel,
    assert_can_complete,
    ensure_no_conflict,
    is_pre_payment,
    mark_canceled,
    validate_booking_dates,
)
from bookings.models import Booking
from chat.models import Message as ChatMessage
from chat.models import create_system_message
from core.settings_resolver import get_int
from listings.services import compute_booking_totals
from notifications import tasks as notification_tasks
from operator_bookings.models import BookingEvent
from payments_cancellation_policy import compute_refund_amounts
from payments_refunds import apply_cancellation_settlement

logger = logging.getLogger(__name__)


def _record_event(booking: Booking, *, type_value: str, payload: dict, actor) -> None:
    try:
        BookingEvent.objects.create(
            booking=booking,
            actor=actor,
            type=type_value,
            payload=payload,
        )
    except Exception:
        logger.exception(
            "booking_event: failed to record %s", type_value, extra={"booking_id": booking.id}
        )


def force_cancel_booking(
    booking: Booking, *, actor: str, reason: str | None = None, operator_user=None
) -> Booking:
    if booking.status == Booking.Status.CANCELED:
        return booking

    assert_can_cancel(booking, actor=actor)
    cancel_reason = (reason or booking.canceled_reason or "").strip() or None
    prev_status = booking.status
    update_fields = [
        "status",
        "canceled_by",
        "canceled_reason",
        "auto_canceled",
        "updated_at",
    ]

    if is_pre_payment(booking):
        with transaction.atomic():
            mark_canceled(booking, actor=actor, auto=False, reason=cancel_reason)
            booking.save(update_fields=update_fields)
            _record_event(
                booking,
                type_value=BookingEvent.Type.STATUS_CHANGE,
                payload={"from": prev_status, "to": booking.status, "reason": cancel_reason or ""},
                actor=operator_user,
            )
            _record_event(
                booking,
                type_value=BookingEvent.Type.OPERATOR_ACTION,
                payload={"action": "force_cancel", "actor": actor, "reason": cancel_reason},
                actor=operator_user,
            )
    else:
        settlement = compute_refund_amounts(
            booking=booking,
            actor=actor,
            today=timezone.localdate(),
        )
        apply_cancellation_settlement(booking, settlement)
        with transaction.atomic():
            mark_canceled(booking, actor=actor, auto=False, reason=cancel_reason)
            booking.save(update_fields=update_fields)
            _record_event(
                booking,
                type_value=BookingEvent.Type.STATUS_CHANGE,
                payload={"from": prev_status, "to": booking.status, "reason": cancel_reason or ""},
                actor=operator_user,
            )
            _record_event(
                booking,
                type_value=BookingEvent.Type.OPERATOR_ACTION,
                payload={"action": "force_cancel", "actor": actor, "reason": cancel_reason},
                actor=operator_user,
            )

    try:
        create_system_message(
            booking,
            ChatMessage.SYSTEM_BOOKING_CANCELLED,
            "Booking cancelled",
            close_chat=True,
        )
    except Exception:
        logger.info(
            "chat: failed to append cancellation message",
            exc_info=True,
            extra={"booking_id": booking.id},
        )

    if booking.renter_id:
        try:
            notification_tasks.send_booking_status_email.delay(
                booking.renter_id,
                booking.id,
                booking.status,
            )
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_status_email",
                exc_info=True,
                extra={"booking_id": booking.id},
            )

    return booking


def force_complete_booking(booking: Booking, *, operator_user=None) -> Booking:
    if booking.status == Booking.Status.CANCELED:
        raise ValidationError({"status": ["Cannot complete a canceled booking."]})
    if booking.status == Booking.Status.COMPLETED:
        return booking

    now = timezone.now()
    prev_status = booking.status
    update_fields = ["status", "updated_at"]
    if booking.return_confirmed_at is None:
        booking.return_confirmed_at = now
        update_fields.insert(1, "return_confirmed_at")

    assert_can_complete(booking)

    if "return_confirmed_at" not in update_fields and booking.return_confirmed_at is None:
        booking.return_confirmed_at = now

    booking.status = Booking.Status.COMPLETED
    if booking.dispute_window_expires_at is None:
        anchor = booking.return_confirmed_at or now
        filing_window_hours = get_int("DISPUTE_FILING_WINDOW_HOURS", 24)
        booking.dispute_window_expires_at = anchor + timedelta(hours=filing_window_hours)
        update_fields.insert(2, "dispute_window_expires_at")

    with transaction.atomic():
        booking.save(update_fields=update_fields)
        _record_event(
            booking,
            type_value=BookingEvent.Type.STATUS_CHANGE,
            payload={"from": prev_status, "to": Booking.Status.COMPLETED},
            actor=operator_user,
        )
        _record_event(
            booking,
            type_value=BookingEvent.Type.OPERATOR_ACTION,
            payload={"action": "force_complete"},
            actor=operator_user,
        )

    try:
        create_system_message(
            booking,
            ChatMessage.SYSTEM_BOOKING_COMPLETED,
            "Booking completed",
            close_chat=True,
        )
    except Exception:
        logger.info(
            "chat: failed to append completion message",
            exc_info=True,
            extra={"booking_id": booking.id},
        )

    if booking.renter_id:
        try:
            notification_tasks.send_booking_completed_email.delay(booking.renter_id, booking.id)
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_completed_email",
                exc_info=True,
                extra={"booking_id": booking.id},
            )

    return booking


def adjust_booking_dates(
    booking: Booking, *, start_date: date, end_date: date, operator_user=None
) -> Booking:
    validate_booking_dates(start_date, end_date)
    if booking.is_terminal():
        raise ValidationError({"status": ["Cannot adjust a canceled or completed booking."]})

    ensure_no_conflict(
        booking.listing,
        start_date,
        end_date,
        exclude_booking_id=booking.id,
    )

    totals = compute_booking_totals(
        listing=booking.listing,
        start_date=start_date,
        end_date=end_date,
    )
    with transaction.atomic():
        booking.start_date = start_date
        booking.end_date = end_date
        booking.totals = totals
        booking.save(update_fields=["start_date", "end_date", "totals", "updated_at"])
        _record_event(
            booking,
            type_value=BookingEvent.Type.OPERATOR_ACTION,
            payload={
                "action": "adjust_dates",
                "start_date": str(start_date),
                "end_date": str(end_date),
            },
            actor=operator_user,
        )
    return booking


def resend_booking_notifications(
    booking: Booking, *, types: Iterable[str], operator_user=None
) -> tuple[list[str], list[str]]:
    queued: list[str] = []
    failed: list[str] = []
    seen: set[str] = set()

    for type_value in types:
        if type_value in seen:
            continue
        seen.add(type_value)
        try:
            if type_value == "booking_request":
                notification_tasks.send_booking_request_email.delay(booking.owner_id, booking.id)
            elif type_value == "status_update":
                notification_tasks.send_booking_status_email.delay(
                    booking.renter_id, booking.id, booking.status
                )
            elif type_value == "receipt":
                notification_tasks.send_booking_payment_receipt_email.delay(
                    booking.renter_id, booking.id
                )
            elif type_value == "completed":
                notification_tasks.send_booking_completed_email.delay(booking.renter_id, booking.id)
            elif type_value == "dispute_missing_evidence":
                # Target the most recent missing-evidence dispute
                dispute = (
                    booking.dispute_cases.filter(
                        status="intake_missing_evidence", intake_evidence_due_at__isnull=False
                    )
                    .order_by("-created_at")
                    .first()
                )
                if dispute:
                    notification_tasks.send_dispute_missing_evidence_email.delay(dispute.id)
                    notification_tasks.send_dispute_missing_evidence_sms.delay(dispute.id)
                else:
                    raise ValueError("No intake-missing-evidence dispute to remind")
            else:
                continue
            queued.append(type_value)
        except Exception:
            failed.append(type_value)
            logger.info(
                "notifications: failed to queue resend",
                exc_info=True,
                extra={"booking_id": booking.id, "type": type_value},
            )

    _record_event(
        booking,
        type_value=BookingEvent.Type.OPERATOR_ACTION,
        payload={"action": "resend_notifications", "types": queued, "failed": failed or []},
        actor=operator_user,
    )
    return queued, failed
