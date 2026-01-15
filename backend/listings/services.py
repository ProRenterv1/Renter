from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Q, QuerySet

from core.settings_resolver import get_int
from payments.tax import (
    compute_fee_with_gst,
    platform_gst_enabled,
    platform_gst_number,
    platform_gst_rate,
)

from .models import Listing


def search_listings(
    qs: QuerySet[Listing],
    q: str | None,
    price_min: float | None,
    price_max: float | None,
    category: str | None = None,
    city: str | None = None,
    owner_id: int | None = None,
) -> QuerySet[Listing]:
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(city__icontains=q))
    if price_min is not None:
        qs = qs.filter(daily_price_cad__gte=price_min)
    if price_max is not None:
        qs = qs.filter(daily_price_cad__lte=price_max)
    if category:
        qs = qs.filter(category__slug=category)
    if city:
        qs = qs.filter(city__iexact=city)
    if owner_id is not None:
        qs = qs.filter(owner_id=owner_id)
    return qs.filter(is_active=True, is_available=True, is_deleted=False).order_by("-created_at")


def compute_booking_totals(
    *,
    listing: Listing,
    start_date: date,
    end_date: date,
    renter_fee_bps_override: int | None = None,
    owner_fee_bps_override: int | None = None,
) -> dict[str, str | bool]:
    """
    Compute pricing totals for a booking:
    - Base price: days * listing.daily_price_cad
    - Renter fee: settings.BOOKING_RENTER_FEE_RATE * base
    - Owner fee: settings.BOOKING_OWNER_FEE_RATE * base
    - Optional renter/owner fee overrides (bps) can force a specific rate;
      negative values are ignored.
    - Total charge: base + renter_fee_total + damage_deposit
    - Owner payout: base - owner_fee_total
    - GST (platform-only) is applied to renter/owner fees when enabled.

    All monetary values are returned as strings (quantized to 2 decimals)
    for stable JSON storage in Booking.totals. Non-monetary flags (e.g. gst_enabled)
    are returned as native types.
    """
    if end_date <= start_date:
        raise ValueError("end_date must be after start_date")

    days = (end_date - start_date).days
    if days <= 0:
        raise ValueError("Booking must be at least one full day long.")

    price_per_day: Decimal = listing.daily_price_cad
    damage_deposit: Decimal = listing.damage_deposit_cad or Decimal("0.00")

    def q2(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    base_amount = q2(price_per_day * days)

    default_platform_fee_bps = int(
        (settings.BOOKING_RENTER_FEE_RATE * Decimal("10000")).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )
    default_owner_fee_bps = int(
        (settings.BOOKING_OWNER_FEE_RATE * Decimal("10000")).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )

    def _resolve_bps(override: int | None, setting_key: str, default_value: int) -> int:
        if override is not None:
            try:
                return max(int(override), 0)
            except (TypeError, ValueError):
                return max(default_value, 0)
        candidate = get_int(setting_key, default_value)
        return candidate if candidate >= 0 else default_value

    platform_fee_bps = _resolve_bps(
        renter_fee_bps_override, "BOOKING_PLATFORM_FEE_BPS", default_platform_fee_bps
    )
    owner_fee_bps = _resolve_bps(
        owner_fee_bps_override, "BOOKING_OWNER_FEE_BPS", default_owner_fee_bps
    )

    renter_fee_rate = Decimal(platform_fee_bps) / Decimal("10000")
    owner_fee_rate = Decimal(owner_fee_bps) / Decimal("10000")

    renter_fee_base = q2(base_amount * renter_fee_rate)
    owner_fee_base = q2(base_amount * owner_fee_rate)
    _, renter_fee_gst, renter_fee_total = compute_fee_with_gst(renter_fee_base)
    _, owner_fee_gst, owner_fee_total = compute_fee_with_gst(owner_fee_base)
    platform_fee_total = q2(renter_fee_total + owner_fee_total)
    owner_payout = q2(base_amount - owner_fee_total)
    total_charge = q2(base_amount + renter_fee_total + damage_deposit)

    if owner_payout < Decimal("0"):
        raise ValueError("Owner payout cannot be negative.")
    if total_charge <= Decimal("0"):
        raise ValueError("Total charge must be greater than zero.")

    gst_enabled = platform_gst_enabled()
    gst_rate = platform_gst_rate()
    gst_number = platform_gst_number() if gst_enabled else ""

    return {
        "days": str(days),
        "daily_price_cad": str(q2(price_per_day)),
        "rental_subtotal": str(base_amount),
        # renter-facing platform fee (backwards-compatible with old name)
        "service_fee": str(renter_fee_base),
        "renter_fee": str(renter_fee_base),
        "renter_fee_base": str(renter_fee_base),
        "renter_fee_gst": str(renter_fee_gst),
        "renter_fee_total": str(renter_fee_total),
        "owner_fee": str(owner_fee_base),
        "owner_fee_base": str(owner_fee_base),
        "owner_fee_gst": str(owner_fee_gst),
        "owner_fee_total": str(owner_fee_total),
        "platform_fee_total": str(platform_fee_total),
        "owner_payout": str(owner_payout),
        "damage_deposit": str(q2(damage_deposit)),
        "total_charge": str(total_charge),
        "gst_enabled": gst_enabled,
        "gst_rate": str(q2(gst_rate)),
        "gst_number": gst_number or "",
    }
