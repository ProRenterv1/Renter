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
from promotions.models import PromotedSlot
from storage import s3 as storage_s3

_TWO_PLACES = Decimal("0.01")
_ZERO = Decimal("0.00")
_BRAND_COLOR = (79 / 255, 134 / 255, 182 / 255)  # Kitoro blue
_BRAND_MUTED_BG = (243 / 255, 248 / 255, 252 / 255)
_TEXT_PRIMARY = (31 / 255, 42 / 255, 61 / 255)
_TEXT_MUTED = (80 / 255, 90 / 255, 105 / 255)


@dataclass(frozen=True)
class _PaymentBreakdown:
    rent: Decimal
    service_fee: Decimal
    damage_deposit: Decimal
    total_charge: Decimal


@dataclass(frozen=True)
class _PromotionPaymentBreakdown:
    base_price: Decimal
    gst: Decimal
    total_charge: Decimal
    price_per_day: Decimal
    duration_days: int


def _cents_to_decimal(value: int | Decimal) -> Decimal:
    return (Decimal(value) / Decimal("100")).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


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

    payment_dt = booking.updated_at or booking.created_at
    if payment_dt:
        if timezone.is_aware(payment_dt):
            payment_dt_local = timezone.localtime(payment_dt)
        else:
            payment_dt_local = payment_dt
        payment_display = _format_date(payment_dt_local.date())
    else:
        payment_display = "N/A"

    duration_days = _extract_duration_days(booking, totals)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Kitoro Rental Receipt")

    width, height = letter
    margin = 0.9 * inch
    y = height - margin

    business_name = "Kitoro"
    business_email = "asterokamax@gmail.com"

    # Background and header
    pdf.saveState()
    pdf.setFillColorRGB(*_BRAND_MUTED_BG)
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    header_height = 1.0 * inch
    pdf.setFillColorRGB(*_BRAND_COLOR)
    pdf.rect(0, height - header_height, width, header_height, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(margin, height - 0.65 * inch, business_name)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, height - 0.82 * inch, business_email)
    pdf.restoreState()
    y = height - header_height - 0.3 * inch

    def new_section(title: str, *, spacing: float = 0.22) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColorRGB(*_BRAND_COLOR)
        pdf.drawString(margin, y, title)
        pdf.setFillColorRGB(*_TEXT_PRIMARY)
        y -= spacing * inch

    def draw_row(label: str, value: str, *, label_width: float = 2.0) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColorRGB(*_TEXT_PRIMARY)
        pdf.drawString(margin, y, label)
        pdf.setFont("Helvetica", 10)
        pdf.setFillColorRGB(*_TEXT_MUTED)
        pdf.drawString(margin + label_width * inch, y, value)
        y -= 0.18 * inch

    pdf.setStrokeColorRGB(0.85, 0.85, 0.85)
    pdf.setFillColorRGB(*_TEXT_PRIMARY)

    header_x = width - margin - 2.6 * inch
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(header_x, y, f"Receipt No: {booking_id}")
    pdf.drawString(header_x, y - 0.18 * inch, f"Issued on: {created_display}")
    pdf.drawString(header_x, y - 0.36 * inch, f"Payment date: {payment_display}")
    y -= 0.65 * inch

    pdf.line(margin, y, width - margin, y)
    y -= 0.25 * inch

    new_section("Booking", spacing=0.2)
    draw_row("Tool", listing_title)
    draw_row("Date range", date_range_display)
    draw_row("Total duration", duration_days)
    draw_row("Owner", owner_name)
    draw_row("Booking ID", str(booking_id))
    y -= 0.1 * inch

    new_section("Payment breakdown", spacing=0.2)
    draw_row("Rent price", _format_currency(breakdown.rent))
    draw_row("Service fee", _format_currency(breakdown.service_fee))
    draw_row("Damage deposit", _format_currency(breakdown.damage_deposit))
    y -= 0.1 * inch

    new_section("Client", spacing=0.2)
    draw_row("Name", renter_name)
    renter_email = getattr(getattr(booking, "renter", None), "email", "") or "N/A"
    renter_phone = getattr(getattr(booking, "renter", None), "phone", "") or "N/A"
    draw_row("Email", renter_email)
    draw_row("Phone", renter_phone)
    y -= 0.1 * inch

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


def render_promotion_receipt_pdf(slot: PromotedSlot) -> bytes:
    """
    Render a PDF receipt for a promotion payment.
    """
    duration_days = _promotion_duration_days(slot)
    breakdown = _PromotionPaymentBreakdown(
        base_price=_cents_to_decimal(getattr(slot, "base_price_cents", 0)),
        gst=_cents_to_decimal(getattr(slot, "gst_cents", 0)),
        total_charge=_cents_to_decimal(getattr(slot, "total_price_cents", 0)),
        price_per_day=_cents_to_decimal(getattr(slot, "price_per_day_cents", 0)),
        duration_days=duration_days,
    )

    owner_name = _display_name(getattr(slot, "owner", None))
    listing = getattr(slot, "listing", None)
    listing_title = getattr(listing, "title", "Listing")
    listing_city = getattr(listing, "city", "") or "N/A"

    start_date = _local_date(getattr(slot, "starts_at", None))
    end_date_exclusive = _local_date(getattr(slot, "ends_at", None))
    inclusive_end = (end_date_exclusive - timedelta(days=1)) if end_date_exclusive else None

    created_at = _local_date(getattr(slot, "created_at", None))
    updated_at = _local_date(getattr(slot, "updated_at", None))
    issued_display = _format_date(created_at)
    payment_display = _format_date(updated_at)

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Kitoro Promotion Receipt")

    width, height = letter
    margin = 0.9 * inch
    y = height - margin

    business_name = "Kitoro"
    business_email = "asterokamax@gmail.com"
    receipt_id = getattr(slot, "id", None) or getattr(slot, "pk", None) or "N/A"

    # Background and header
    pdf.saveState()
    pdf.setFillColorRGB(*_BRAND_MUTED_BG)
    pdf.rect(0, 0, width, height, stroke=0, fill=1)
    header_height = 1.0 * inch
    pdf.setFillColorRGB(*_BRAND_COLOR)
    pdf.rect(0, height - header_height, width, header_height, stroke=0, fill=1)
    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(margin, height - 0.65 * inch, business_name)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(margin, height - 0.82 * inch, business_email)
    pdf.restoreState()
    y = height - header_height - 0.3 * inch

    def new_section(title: str, *, spacing: float = 0.22) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColorRGB(*_BRAND_COLOR)
        pdf.drawString(margin, y, title)
        pdf.setFillColorRGB(*_TEXT_PRIMARY)
        y -= spacing * inch

    def draw_row(label: str, value: str, *, label_width: float = 2.0) -> None:
        nonlocal y
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColorRGB(*_TEXT_PRIMARY)
        pdf.drawString(margin, y, label)
        pdf.setFont("Helvetica", 10)
        pdf.setFillColorRGB(*_TEXT_MUTED)
        pdf.drawString(margin + label_width * inch, y, value)
        y -= 0.18 * inch

    pdf.setStrokeColorRGB(0.85, 0.85, 0.85)
    pdf.setFillColorRGB(*_TEXT_PRIMARY)

    header_x = width - margin - 2.6 * inch
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(header_x, y, f"Receipt No: {receipt_id}")
    pdf.drawString(header_x, y - 0.18 * inch, f"Issued on: {issued_display}")
    pdf.drawString(header_x, y - 0.36 * inch, f"Payment date: {payment_display}")
    y -= 0.65 * inch

    pdf.line(margin, y, width - margin, y)
    y -= 0.25 * inch

    new_section("Promotion", spacing=0.2)
    draw_row("Listing", listing_title)
    draw_row("Promotion window", _format_date_range(start_date, inclusive_end))
    duration_display = f"{duration_days} days" if duration_days else "N/A"
    draw_row("Total duration", duration_display)
    draw_row("City", listing_city)
    draw_row("Promotion ID", str(receipt_id))
    y -= 0.1 * inch

    new_section("Payment breakdown", spacing=0.2)
    draw_row("Price per day", _format_currency(breakdown.price_per_day))
    draw_row("Promotion price", _format_currency(breakdown.base_price))
    draw_row("GST (5%)", _format_currency(breakdown.gst))
    draw_row("Total charged", _format_currency(breakdown.total_charge))
    y -= 0.1 * inch

    new_section("Client", spacing=0.2)
    owner_email = getattr(getattr(slot, "owner", None), "email", "") or "N/A"
    draw_row("Name", owner_name)
    draw_row("Email", owner_email)
    y -= 0.1 * inch

    pdf.showPage()
    pdf.save()

    return buffer.getvalue()


def upload_promotion_receipt_pdf(slot: PromotedSlot) -> Tuple[str, str, bytes]:
    """
    Generate and upload a promotion receipt PDF to S3.

    Returns a tuple of (key, url, pdf_bytes) for the uploaded file.
    """
    if not slot.id:
        raise ValueError("Promotion slot must be persisted before generating a receipt.")

    pdf_bytes = render_promotion_receipt_pdf(slot)
    key = f"uploads/private/receipts/promotions/{slot.id}_promotion_receipt.pdf"

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


def _local_date(value):
    if not value:
        return None
    candidate = timezone.localtime(value) if timezone.is_aware(value) else value
    if hasattr(candidate, "date"):
        return candidate.date()
    return None


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


def _extract_duration_days(booking: Booking, totals: Mapping[str, object]) -> str:
    total_days = totals.get("days")
    if total_days not in (None, ""):
        return f"{total_days} days"
    start = booking.start_date
    end = booking.end_date
    if start and end:
        delta = (end - start).days
        if delta <= 0:
            delta = 1
        return f"{delta} days"
    return "N/A"


def _promotion_duration_days(slot: PromotedSlot) -> int:
    start = getattr(slot, "starts_at", None)
    end = getattr(slot, "ends_at", None)
    if start and end:
        start_local = timezone.localtime(start) if timezone.is_aware(start) else start
        end_local = timezone.localtime(end) if timezone.is_aware(end) else end
        delta = (end_local - start_local).days
        return max(delta, 1)
    return 0


__all__ = [
    "render_booking_receipt_pdf",
    "upload_booking_receipt_pdf",
    "render_promotion_receipt_pdf",
    "upload_promotion_receipt_pdf",
]
