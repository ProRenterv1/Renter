from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from notifications import tasks as notification_tasks

from .models import DisputeCase, DisputeEvidence, DisputeMessage

logger = logging.getLogger(__name__)


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

            now = timezone.now()
            update_fields: list[str] = []

            if dispute.status != DisputeCase.Status.AWAITING_REBUTTAL:
                dispute.status = DisputeCase.Status.AWAITING_REBUTTAL
                update_fields.append("status")

            new_rebuttal_due_at = dispute.rebuttal_due_at
            if new_rebuttal_due_at is None or new_rebuttal_due_at <= now:
                new_rebuttal_due_at = now + timedelta(hours=24)
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

    for dispute in candidates:
        counterparty_id = get_counterparty_user_id(dispute)
        if not counterparty_id or not dispute.rebuttal_due_at:
            continue

        window_start = dispute.rebuttal_due_at - timedelta(hours=24)

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
