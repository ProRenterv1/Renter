"""Celery tasks for bookings."""

from __future__ import annotations

import logging
from datetime import date

from celery import shared_task
from django.utils import timezone

from notifications import tasks as notification_tasks

from .domain import is_pre_payment, mark_canceled
from .models import Booking

logger = logging.getLogger(__name__)

EXPIRED_REASON = "Booking expired before payment."


@shared_task(name="bookings.auto_expire_stale_bookings")
def auto_expire_stale_bookings() -> int:
    """
    Cancel stale, pre-payment bookings that never moved forward.

    Returns the number of bookings automatically expired.
    """
    today: date = timezone.localdate()
    expired_count = 0
    update_fields = [
        "status",
        "canceled_by",
        "canceled_reason",
        "auto_canceled",
        "updated_at",
    ]

    requested_qs = Booking.objects.filter(
        status=Booking.Status.REQUESTED,
        start_date__lte=today,
    ).select_related("listing", "owner", "renter")

    confirmed_qs = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_date__lte=today,
    ).select_related("listing", "owner", "renter")

    def _expire_booking(booking: Booking) -> None:
        nonlocal expired_count
        if booking.is_terminal():
            return
        mark_canceled(booking, actor="system", auto=True, reason=EXPIRED_REASON)
        booking.save(update_fields=update_fields)
        expired_count += 1
        try:
            notification_tasks.send_booking_expired_email.delay(booking.id)
        except Exception:
            logger.info(
                "notifications: failed to queue booking_expired_email",
                extra={"booking_id": booking.id},
                exc_info=True,
            )

    for booking in requested_qs:
        _expire_booking(booking)

    for booking in confirmed_qs:
        if not is_pre_payment(booking):
            continue
        _expire_booking(booking)

    return expired_count
