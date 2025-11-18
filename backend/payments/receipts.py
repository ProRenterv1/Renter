"""Utilities for rendering booking payment receipts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from typing import Iterable, Mapping, Tuple

from django.conf import settings
from django.utils import timezone
from reportlab.lib.pagesizes import letter  # Requires reportlab package.
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from bookings.models import Booking
from storage import s3 as storage_s3

_TWO_PLACES = Decimal("0.01")
_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class _PaymentBreakdown:
    rent: Decimal
    service_fee: Decimal
    damage_deposit: Decimal
    total_charge: Decimal


def render_booking_receipt_pdf(booking: Booking) -> bytes:
    """
    Render a PDF receipt for a paid booking.

    The function is pure – it only reads data from the Booking instance and
    returns the rendered PDF bytes.
    """
    totals: Mapping[str, str | int | float | Decimal] = booking.totals or {}
    breakdown = _extract_payment_breakdown(totals)

    renter_name = _display_name(getattr(booking, "renter", None))
    owner_name = _display_name(getattr(booking, "owner", None))
    listing_title = getattr(getattr(booking, "listing", None), "title", "Listing")

    start_date = booking.start_date
    end_date = booking.end_date or booking.start_date
    inclusive_end = (end_date - timedelta(days=1)) if end_date else start_date
    date_range_display = _format_date_range(start_date, inclusive_end)

    created_at = booking.created_at
    if created_at:
        if timezone.is_aware(created_at):
            created_dt = timezone.localtime(created_at)
        else:
            created_dt = created_at
        created_display = _format_date(created_dt.date())
    else:
        created_display = "N/A"
    booking_id = getattr(booking, "id", None) or getattr(booking, "pk", None) or "N/A"

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Rental Payment Receipt")

    width, height = letter
    margin = 0.9 * inch
    y = height - margin

    def new_section(title: str) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(margin, y, title)
        y -= 0.22 * inch

    def draw_row(label: str, value: str) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(margin, y, label)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(margin + 1.9 * inch, y, value)
        y -= 0.18 * inch

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(margin, y, "Rental Payment Receipt")
    y -= 0.35 * inch

    new_section("Parties")
    draw_row("Renter", renter_name)
    draw_row("Owner", owner_name)
    draw_row("Listing", listing_title)
    y -= 0.12 * inch

    new_section("Booking Details")
    draw_row("Booking ID", str(booking_id))
    draw_row("Date range", date_range_display)
    draw_row("Created", created_display)
    y -= 0.12 * inch

    new_section("Payment Breakdown")
    draw_row("Rent", _format_currency(breakdown.rent))
    draw_row("Service fee", _format_currency(breakdown.service_fee))
    draw_row("Damage deposit", _format_currency(breakdown.damage_deposit))
    y -= 0.04 * inch
    draw_row("Total paid", _format_currency(breakdown.total_charge))
    y -= 0.12 * inch

    new_section("Payment References")
    draw_row("Charge PaymentIntent", booking.charge_payment_intent_id or "N/A")
    if booking.deposit_hold_id:
        draw_row("Deposit PaymentIntent", booking.deposit_hold_id)

    pdf.showPage()
    pdf.save()

    return buffer.getvalue()


def upload_booking_receipt_pdf(booking: Booking) -> Tuple[str, str, bytes]:
    """
    Generate and upload a booking receipt PDF to S3.

    Returns a tuple of (key, url, pdf_bytes) for the uploaded file.
    """
    if not booking.id:
        raise ValueError("Booking must be persisted before generating a receipt.")

    pdf_bytes = render_booking_receipt_pdf(booking)
    key = f"uploads/private/receipts/{booking.id}_receipt.pdf"

    storage_s3._client().put_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Body=pdf_bytes,
        ContentType="application/pdf",
    )
    url = storage_s3.public_url(key)
    return key, url, pdf_bytes


def _extract_payment_breakdown(totals: Mapping[str, object]) -> _PaymentBreakdown:
    rent = _get_amount(totals, ("rental_subtotal",))
    service_fee = _get_amount(totals, ("renter_fee", "service_fee"))
    damage_deposit = _get_amount(totals, ("damage_deposit",))
    total_charge = _get_amount(totals, ("total_charge",), required=True)
    return _PaymentBreakdown(
        rent=rent,
        service_fee=service_fee,
        damage_deposit=damage_deposit,
        total_charge=total_charge,
    )


def _get_amount(
    totals: Mapping[str, object],
    keys: Iterable[str],
    *,
    required: bool = False,
) -> Decimal:
    for key in keys:
        value = totals.get(key)
        if value not in (None, ""):
            return _to_decimal(value)
    if required:
        joined = "/".join(keys)
        raise ValueError(f"Booking totals missing required value '{joined}'.")
    return _ZERO


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        amount = value
    else:
        amount = Decimal(str(value))
    return amount.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _format_currency(amount: Decimal) -> str:
    return f"CAD {amount:,.2f}"


def _display_name(user) -> str:
    if not user:
        return "Unknown"
    if hasattr(user, "get_full_name"):
        full_name = (user.get_full_name() or "").strip()
    else:
        full_name = ""
    if not full_name:
        first = (getattr(user, "first_name", "") or "").strip()
        last = (getattr(user, "last_name", "") or "").strip()
        full_name = " ".join(part for part in (first, last) if part)
    if not full_name:
        username = getattr(user, "username", "") or ""
        if username:
            return username
        return str(user)
    return full_name


def _format_date_range(start: date | None, end: date | None) -> str:
    if not start and not end:
        return "N/A"
    if start and not end:
        return _format_date(start)
    if end and not start:
        return _format_date(end)
    return f"{_format_date(start)} - {_format_date(end)}"


def _format_date(value: date | None) -> str:
    if not value:
        return "N/A"
    month = value.strftime("%b")
    return f"{month} {value.day}, {value.year}"


__all__ = ["render_booking_receipt_pdf", "upload_booking_receipt_pdf"]
