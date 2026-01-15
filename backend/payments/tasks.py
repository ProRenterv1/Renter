from __future__ import annotations

import logging

from celery import shared_task
from django.db.models import Exists, OuterRef
from django.utils import timezone

from bookings.models import Booking
from payments.models import Transaction
from payments.stripe_api import create_owner_transfer_for_booking

logger = logging.getLogger(__name__)

# Ensure auxiliary tasks are registered with Celery.
from payments import tasks_tax_invoices as _tasks_tax_invoices  # noqa: F401,E402


@shared_task(name="payments.process_owner_payouts")
def process_owner_payouts():
    """
    Transfer owner payouts for bookings past the dispute window.
    Safe to run repeatedly; skips bookings already paid out.
    """
    now = timezone.now()
    owner_payout_exists = Transaction.objects.filter(
        user_id=OuterRef("owner_id"),
        booking_id=OuterRef("pk"),
        kind=Transaction.Kind.OWNER_EARNING,
    )
    eligible_qs = (
        Booking.objects.filter(
            return_confirmed_at__isnull=False,
            dispute_window_expires_at__lt=now,
            is_disputed=False,
            status__in=[Booking.Status.PAID, Booking.Status.COMPLETED],
        )
        .annotate(has_owner_payout=Exists(owner_payout_exists))
        .filter(has_owner_payout=False)
        .select_related("listing", "owner")
    )

    bookings = list(eligible_qs)
    processed = 0
    for booking in bookings:
        try:
            create_owner_transfer_for_booking(
                booking=booking, payment_intent_id=booking.charge_payment_intent_id
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "owner payout task failed for booking %s: %s", booking.id, exc, exc_info=True
            )
    return {"processed": processed, "checked": len(bookings)}
