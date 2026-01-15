from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from bookings.models import Booking
from notifications.tasks import send_owner_fee_invoice_email
from payments.models import OwnerFeeTaxInvoice
from payments.tax import platform_gst_number

logger = logging.getLogger(__name__)


def _safe_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _previous_month_range(today: date) -> tuple[date, date]:
    first_of_month = today.replace(day=1)
    last_prev_month = first_of_month - timedelta(days=1)
    period_start = last_prev_month.replace(day=1)
    return period_start, last_prev_month


def _invoice_number(owner_id: int, period_start: date) -> str:
    yyyymm = period_start.strftime("%Y%m")
    prefix = f"INV-{yyyymm}-{owner_id}-"
    seq = OwnerFeeTaxInvoice.objects.filter(invoice_number__startswith=prefix).count() + 1
    return f"{prefix}{seq:03d}"


@shared_task(name="payments.generate_owner_fee_tax_invoices")
def generate_owner_fee_tax_invoices() -> dict[str, int]:
    """
    Generate monthly owner fee tax invoices for the previous month.
    """
    today = timezone.localdate()
    period_start, period_end = _previous_month_range(today)

    bookings = (
        Booking.objects.filter(
            status=Booking.Status.PAID,
            paid_at__date__gte=period_start,
            paid_at__date__lte=period_end,
        )
        .select_related("owner")
        .only("id", "owner_id", "totals", "paid_at")
    )

    totals_by_owner: dict[int, dict[str, Decimal]] = {}
    for booking in bookings:
        totals = booking.totals or {}
        fee_base = _safe_decimal(totals.get("owner_fee_base") or totals.get("owner_fee"))
        fee_gst = _safe_decimal(totals.get("owner_fee_gst"))
        if fee_base <= Decimal("0.00") and fee_gst <= Decimal("0.00"):
            continue
        bucket = totals_by_owner.setdefault(
            booking.owner_id, {"fee_subtotal": Decimal("0.00"), "fee_gst": Decimal("0.00")}
        )
        bucket["fee_subtotal"] += fee_base
        bucket["fee_gst"] += fee_gst

    created = 0
    for owner_id, bucket in totals_by_owner.items():
        fee_subtotal = bucket["fee_subtotal"].quantize(Decimal("0.01"))
        fee_gst = bucket["fee_gst"].quantize(Decimal("0.01"))
        total = (fee_subtotal + fee_gst).quantize(Decimal("0.01"))
        if total <= Decimal("0.00"):
            continue

        exists = OwnerFeeTaxInvoice.objects.filter(
            owner_id=owner_id,
            period_start=period_start,
            period_end=period_end,
        ).exists()
        if exists:
            continue

        with transaction.atomic():
            invoice = OwnerFeeTaxInvoice.objects.create(
                owner_id=owner_id,
                period_start=period_start,
                period_end=period_end,
                fee_subtotal=fee_subtotal,
                gst=fee_gst,
                total=total,
                invoice_number=_invoice_number(owner_id, period_start),
                gst_number_snapshot=platform_gst_number() or "",
            )
            created += 1

        try:
            send_owner_fee_invoice_email.delay(invoice.id)
        except Exception:
            logger.info(
                "notifications: could not queue send_owner_fee_invoice_email",
                exc_info=True,
            )

    return {"created": created, "owners": len(totals_by_owner)}
