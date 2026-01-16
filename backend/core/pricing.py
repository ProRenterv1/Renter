from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.http import JsonResponse

from core.settings_resolver import get_int
from payments.tax import platform_gst_enabled, platform_gst_rate


def _rate_to_bps(rate: Decimal) -> int:
    """Convert a decimal rate (e.g. 0.10) to basis points."""
    try:
        return int((rate * Decimal("10000")).to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        return 0


def pricing_summary(_request):
    """
    Public endpoint that surfaces the platform's current fee configuration.

    Values account for operator overrides stored via DbSetting when present.
    """

    default_renter_bps = _rate_to_bps(settings.BOOKING_RENTER_FEE_RATE)
    default_owner_bps = _rate_to_bps(settings.BOOKING_OWNER_FEE_RATE)
    default_instant_bps = _rate_to_bps(settings.INSTANT_PAYOUT_FEE_RATE)

    renter_bps = max(get_int("BOOKING_PLATFORM_FEE_BPS", default_renter_bps), 0)
    owner_bps = max(get_int("BOOKING_OWNER_FEE_BPS", default_owner_bps), 0)
    instant_bps = max(get_int("INSTANT_PAYOUT_FEE_BPS", default_instant_bps), 0)

    def as_percent(bps: int) -> float:
        return round(bps / 100, 2)

    gst_enabled = platform_gst_enabled()
    gst_rate = platform_gst_rate()

    return JsonResponse(
        {
            "currency": "CAD",
            "renter_fee_bps": renter_bps,
            "renter_fee_rate": as_percent(renter_bps),
            "owner_fee_bps": owner_bps,
            "owner_fee_rate": as_percent(owner_bps),
            "instant_payout_fee_bps": instant_bps,
            "instant_payout_fee_rate": as_percent(instant_bps),
            "gst_enabled": gst_enabled,
            "gst_rate": str(gst_rate),
        }
    )
