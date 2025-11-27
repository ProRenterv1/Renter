from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Q, QuerySet

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
) -> dict[str, str]:
    """
    Compute pricing totals for a booking:
    - Base price: days * listing.daily_price_cad
    - Renter fee: settings.BOOKING_RENTER_FEE_RATE * base
    - Owner fee: settings.BOOKING_OWNER_FEE_RATE * base
    - Total charge: base + renter_fee + damage_deposit
    - Owner payout: base - owner_fee

    All monetary values are returned as strings (quantized to 2 decimals)
    for stable JSON storage in Booking.totals.
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
    renter_fee_rate: Decimal = settings.BOOKING_RENTER_FEE_RATE
    owner_fee_rate: Decimal = settings.BOOKING_OWNER_FEE_RATE

    renter_fee = q2(base_amount * renter_fee_rate)
    owner_fee = q2(base_amount * owner_fee_rate)
    platform_fee_total = q2(renter_fee + owner_fee)
    owner_payout = q2(base_amount - owner_fee)
    total_charge = q2(base_amount + renter_fee + damage_deposit)

    return {
        "days": str(days),
        "daily_price_cad": str(q2(price_per_day)),
        "rental_subtotal": str(base_amount),
        # renter-facing platform fee (backwards-compatible with old name)
        "service_fee": str(renter_fee),
        "renter_fee": str(renter_fee),
        "owner_fee": str(owner_fee),
        "platform_fee_total": str(platform_fee_total),
        "owner_payout": str(owner_payout),
        "damage_deposit": str(q2(damage_deposit)),
        "total_charge": str(total_charge),
    }
