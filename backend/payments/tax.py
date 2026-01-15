from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional, Tuple

from core.settings_resolver import get_bool, get_decimal, get_str

GST_RATE_AB = Decimal("0.05")
_TWO_PLACES = Decimal("0.01")


def round_2(amount: Decimal) -> Decimal:
    return amount.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def platform_gst_enabled() -> bool:
    return get_bool("ORG_GST_REGISTERED", default=False)


def platform_gst_number() -> Optional[str]:
    if not platform_gst_enabled():
        # Stored GST numbers are treated as inactive when GST is disabled.
        return None
    number = get_str("ORG_GST_NUMBER", default="").strip()
    return number or None


def platform_gst_rate() -> Decimal:
    return get_decimal("ORG_GST_RATE", default=GST_RATE_AB)


def compute_gst(amount: Decimal) -> Decimal:
    if not platform_gst_enabled():
        return Decimal("0.00")
    gst = (amount * platform_gst_rate()).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return gst


def compute_fee_with_gst(fee: Decimal) -> Tuple[Decimal, Decimal, Decimal]:
    base = round_2(fee)
    gst = compute_gst(base)
    total = round_2(base + gst)
    return base, gst, total


def split_tax_included(gross: Decimal, rate: Decimal) -> Tuple[Decimal, Decimal]:
    gross_amount = round_2(gross)
    if gross_amount <= Decimal("0.00") or rate <= Decimal("0.00"):
        return gross_amount, Decimal("0.00")
    base = round_2(gross_amount / (Decimal("1.0") + rate))
    tax = round_2(gross_amount - base)
    return base, tax
