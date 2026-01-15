from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from payments.models import OwnerFeeTaxInvoice
from payments.tasks_tax_invoices import generate_owner_fee_tax_invoices

pytestmark = pytest.mark.django_db


def _previous_month_range(today):
    first_of_month = today.replace(day=1)
    last_prev_month = first_of_month - timedelta(days=1)
    period_start = last_prev_month.replace(day=1)
    return period_start, last_prev_month


def test_generate_owner_fee_tax_invoices_sums_bookings(booking_factory, owner_user):
    today = timezone.localdate()
    period_start, period_end = _previous_month_range(today)
    paid_at = timezone.make_aware(datetime.combine(period_start, datetime.min.time()))

    booking = booking_factory(
        owner=owner_user,
        status="paid",
        paid_at=paid_at,
    )
    booking.totals = {
        "owner_fee_base": "5.00",
        "owner_fee_gst": "0.25",
        "owner_fee_total": "5.25",
    }
    booking.save(update_fields=["totals", "paid_at", "status"])

    result = generate_owner_fee_tax_invoices()

    assert result["created"] == 1
    invoice = OwnerFeeTaxInvoice.objects.get(owner=owner_user)
    assert invoice.period_start == period_start
    assert invoice.period_end == period_end
    assert invoice.fee_subtotal == Decimal("5.00")
    assert invoice.gst == Decimal("0.25")
    assert invoice.total == Decimal("5.25")
