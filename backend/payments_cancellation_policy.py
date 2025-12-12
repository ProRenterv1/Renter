"""Business logic for cancellation settlements on paid bookings."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, Mapping, Tuple

from bookings.models import Booking

CancelActor = Literal["renter", "owner", "no_show", "system"]


@dataclass(frozen=True)
class CancellationSettlement:
    """Represents how a canceled booking should settle financially."""

    refund_to_renter: Decimal
    owner_delta: Decimal
    platform_delta: Decimal
    deposit_capture_amount: Decimal
    deposit_release_amount: Decimal


_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _quantize(value: Decimal) -> Decimal:
    """Round a Decimal value to cents using HALF_UP."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _safe_decimal(value: object, default: Decimal) -> Decimal:
    """Convert arbitrary value to Decimal, falling back to default on failure."""
    if isinstance(value, Decimal):
        return _quantize(value)
    try:
        return _quantize(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _get_total_decimal(
    totals: Mapping[str, object] | None,
    key: str,
    default: str | Decimal = "0",
) -> Decimal:
    """
    Safely read a decimal value from booking.totals.

    Missing/malformed values fall back to the provided default.
    """
    if isinstance(default, Decimal):
        fallback = _quantize(default)
    else:
        fallback = _quantize(Decimal(str(default)))
    if isinstance(totals, Mapping) and key in totals:
        return _safe_decimal(totals[key], fallback)
    return fallback


def _parse_days(booking: Booking, totals: Mapping[str, object] | None) -> int:
    """Extract the number of booked days with sensible defaults."""
    raw = None
    if isinstance(totals, Mapping):
        raw = totals.get("days")
    if raw is None:
        raw = booking.days
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return booking.days or 0
    return max(days, 0)


def _per_day_breakdown(
    *,
    days: int,
    rental_subtotal: Decimal,
    renter_fee: Decimal,
    owner_payout: Decimal,
    platform_fee_total: Decimal,
    owner_fee: Decimal,
) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """
    Compute per-day amounts for rent, renter fee, owner payout, and platform fee.
    """
    if days <= 0:
        return _ZERO, _ZERO, _ZERO, _ZERO
    days_decimal = Decimal(days)

    rent_per_day = _quantize(rental_subtotal / days_decimal)
    renter_fee_per_day = _quantize(renter_fee / days_decimal)
    owner_payout_per_day = _quantize(owner_payout / days_decimal)

    platform_total_source = platform_fee_total
    if platform_total_source <= _ZERO and (owner_fee != _ZERO or renter_fee != _ZERO):
        platform_total_source = owner_fee + renter_fee
    platform_fee_per_day = (
        _quantize(platform_total_source / days_decimal) if platform_total_source != _ZERO else _ZERO
    )
    return rent_per_day, renter_fee_per_day, owner_payout_per_day, platform_fee_per_day


def compute_refund_amounts(
    *,
    booking: Booking,
    actor: CancelActor,
    today: date,
) -> CancellationSettlement:
    """Return how cash / deposit should settle for a paid booking cancellation."""

    from bookings.domain import days_until_start

    totals = booking.totals or {}
    rental_subtotal = _get_total_decimal(totals, "rental_subtotal")
    renter_fee = _get_total_decimal(totals, "renter_fee", totals.get("service_fee", "0"))
    owner_fee = _get_total_decimal(totals, "owner_fee")
    owner_payout = _get_total_decimal(totals, "owner_payout")
    platform_fee_total = _get_total_decimal(totals, "platform_fee_total")
    damage_deposit = _get_total_decimal(totals, "damage_deposit")

    if damage_deposit < _ZERO:
        damage_deposit = _ZERO
    days = _parse_days(booking, totals)
    rent_per_day, renter_fee_per_day, owner_payout_per_day, platform_fee_per_day = (
        _per_day_breakdown(
            days=days,
            rental_subtotal=rental_subtotal,
            renter_fee=renter_fee,
            owner_payout=owner_payout,
            platform_fee_total=platform_fee_total,
            owner_fee=owner_fee,
        )
    )

    d = days_until_start(today, booking)

    charge_total = _quantize(rental_subtotal + renter_fee)
    refund_to_renter = charge_total
    owner_delta = -owner_payout
    platform_delta = -platform_fee_total
    deposit_capture_amount = _ZERO
    deposit_release_amount = damage_deposit

    if actor == "renter":
        if d > 1:
            # Full refund scenario already represented by defaults.
            pass
        elif d == 1:
            penalty_charge = rent_per_day + renter_fee_per_day
            penalty_charge = max(_ZERO, min(penalty_charge, charge_total))
            refund_to_renter = _quantize(charge_total - penalty_charge)
            owner_delta = owner_payout_per_day
            platform_delta = platform_fee_per_day
        else:
            penalty_rent = _quantize(rental_subtotal * Decimal("0.5"))
            penalty_fee = _quantize(renter_fee * Decimal("0.5"))
            penalty_charge = penalty_rent + penalty_fee
            penalty_charge = max(_ZERO, min(penalty_charge, charge_total))
            refund_to_renter = _quantize(charge_total - penalty_charge)
            owner_delta = _ZERO
            # Treat same-day penalties as net-new platform revenue.
            platform_delta = penalty_charge
    elif actor == "no_show":
        penalty_rent = _quantize(rental_subtotal * Decimal("0.5"))
        penalty_fee = _quantize(renter_fee * Decimal("0.5"))
        penalty_charge = penalty_rent + penalty_fee
        penalty_charge = max(_ZERO, min(penalty_charge, charge_total))
        refund_to_renter = _quantize(charge_total - penalty_charge)
        owner_delta = _ZERO
        platform_delta = penalty_charge
    elif actor == "owner":
        # Defaults already represent full refund.
        pass
    else:
        # system/unexpected actor -> default to full refund behavior.
        actor = "system"

    refund_to_renter = max(_ZERO, min(refund_to_renter, charge_total))
    deposit_capture_amount = max(_ZERO, min(deposit_capture_amount, damage_deposit))
    remaining_deposit = damage_deposit - deposit_capture_amount
    deposit_release_amount = max(_ZERO, min(deposit_release_amount, remaining_deposit))

    return CancellationSettlement(
        refund_to_renter=_quantize(refund_to_renter),
        owner_delta=_quantize(owner_delta),
        platform_delta=_quantize(platform_delta),
        deposit_capture_amount=_quantize(deposit_capture_amount),
        deposit_release_amount=_quantize(deposit_release_amount),
    )
