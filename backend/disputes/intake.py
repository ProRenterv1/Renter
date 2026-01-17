from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.db import transaction
from django.utils import timezone

from bookings.models import BookingPhoto
from core.redis import push_event
from core.settings_resolver import get_int
from notifications import tasks as notification_tasks

from .models import DisputeCase, DisputeEvidence
from .tasks import start_rebuttal_window

logger = logging.getLogger(__name__)


def _count_clean_booking_photos(booking_id: int) -> tuple[int, int]:
    """Return (before_clean, after_clean) counts for AV-clean booking photos."""
    qs = BookingPhoto.objects.filter(
        booking_id=booking_id,
        av_status=BookingPhoto.AVStatus.CLEAN,
    )
    before_count = qs.filter(role=BookingPhoto.Role.BEFORE).count()
    after_count = qs.filter(role=BookingPhoto.Role.AFTER).count()
    return before_count, after_count


def _count_clean_evidence(dispute_id: int) -> tuple[int, int, int]:
    """
    Return (photo_count, video_count, total_clean) for AV-clean dispute evidence.
    """
    qs = DisputeEvidence.objects.filter(
        dispute_id=dispute_id,
        av_status=DisputeEvidence.AVStatus.CLEAN,
    )
    photo_count = qs.filter(kind=DisputeEvidence.Kind.PHOTO).count()
    video_count = qs.filter(kind=DisputeEvidence.Kind.VIDEO).count()
    total_clean = qs.count()
    return photo_count, video_count, total_clean


def update_dispute_intake_status(dispute_id: int) -> Optional[DisputeCase]:
    """
    Evaluate intake evidence for a dispute and update its status accordingly.

    Returns the updated DisputeCase or None if not found.
    """
    try:
        with transaction.atomic():
            try:
                dispute = (
                    DisputeCase.objects.select_for_update()
                    .select_related("booking", "opened_by")
                    .get(pk=dispute_id)
                )
            except DisputeCase.DoesNotExist:
                logger.warning("dispute intake: dispute %s not found", dispute_id)
                return None

            booking = dispute.booking
            if not booking:
                logger.warning("dispute intake: booking missing for dispute %s", dispute_id)
                return dispute

            if dispute.category in {
                DisputeCase.Category.SAFETY_OR_FRAUD,
                DisputeCase.Category.PICKUP_NO_SHOW,
            }:
                return dispute

            before_clean, after_clean = _count_clean_booking_photos(booking_id=booking.id)
            photo_count, video_count, total_clean = _count_clean_evidence(dispute_id=dispute.id)

            booking_photo_required_categories = {
                DisputeCase.Category.DAMAGE,
                DisputeCase.Category.MISSING_ITEM,
                DisputeCase.Category.NOT_AS_DESCRIBED,
            }

            has_booking_photos = (before_clean + after_clean) > 0

            if dispute.damage_flow_kind == DisputeCase.DamageFlowKind.BROKE_DURING_USE:
                minimum_met = video_count >= 1 or photo_count >= 2
            else:
                minimum_met = total_clean >= 1

            if dispute.category in booking_photo_required_categories and not has_booking_photos:
                minimum_met = False

            new_status: Optional[str]
            now = timezone.now()
            filing_window_hours = get_int("DISPUTE_FILING_WINDOW_HOURS", 24)
            rebuttal_window_hours = get_int("DISPUTE_REBUTTAL_WINDOW_HOURS", 24)
            new_rebuttal_due_at = dispute.rebuttal_due_at
            new_intake_due_at = dispute.intake_evidence_due_at
            status_changed = False
            trigger_rebuttal_task = False

            if not minimum_met:
                new_status = DisputeCase.Status.INTAKE_MISSING_EVIDENCE
                filed_at = dispute.filed_at or now
                new_intake_due_at = filed_at + timedelta(hours=filing_window_hours)
                new_rebuttal_due_at = filed_at + timedelta(hours=rebuttal_window_hours)
            else:
                new_status = DisputeCase.Status.AWAITING_REBUTTAL
                if dispute.status != DisputeCase.Status.AWAITING_REBUTTAL:
                    new_rebuttal_due_at = now + timedelta(hours=rebuttal_window_hours)
                elif new_rebuttal_due_at is None:
                    new_rebuttal_due_at = now + timedelta(hours=rebuttal_window_hours)
                new_intake_due_at = None

            update_fields: list[str] = []
            if dispute.status != new_status:
                dispute.status = new_status
                update_fields.append("status")
                status_changed = True
                if new_status == DisputeCase.Status.AWAITING_REBUTTAL:
                    trigger_rebuttal_task = True
            if new_rebuttal_due_at and dispute.rebuttal_due_at != new_rebuttal_due_at:
                dispute.rebuttal_due_at = new_rebuttal_due_at
                update_fields.append("rebuttal_due_at")
            if dispute.intake_evidence_due_at != new_intake_due_at:
                dispute.intake_evidence_due_at = new_intake_due_at
                update_fields.append("intake_evidence_due_at")

            if update_fields:
                update_fields.append("updated_at")
                dispute.save(update_fields=update_fields)

            if status_changed and dispute.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE:
                try:
                    notification_tasks.send_dispute_missing_evidence_email.delay(dispute.id)
                    notification_tasks.send_dispute_missing_evidence_sms.delay(dispute.id)
                except Exception:
                    logger.info(
                        "dispute intake: could not queue missing evidence email for dispute %s",
                        dispute.id,
                        exc_info=True,
                    )

            if (
                status_changed
                and dispute.status == DisputeCase.Status.AWAITING_REBUTTAL
                and booking
            ):
                payload = {
                    "dispute_id": dispute.id,
                    "booking_id": booking.id,
                    "status": dispute.status,
                }
                for user_id in (booking.owner_id, booking.renter_id):
                    try:
                        push_event(user_id, "dispute:opened", payload)
                    except Exception:
                        logger.info(
                            "dispute intake: failed to push dispute:opened event",
                            extra={"user_id": user_id, "dispute_id": dispute.id},
                            exc_info=True,
                        )

            if trigger_rebuttal_task:
                transaction.on_commit(lambda: start_rebuttal_window.delay(dispute.id))

            return dispute
    except Exception:
        logger.exception("dispute intake: update failed for dispute %s", dispute_id)
        return None
