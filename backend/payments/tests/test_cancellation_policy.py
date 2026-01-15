from __future__ import annotations

from datetime import date
from decimal import Decimal

from bookings.models import Booking
from payments_cancellation_policy import compute_refund_amounts


def _build_paid_booking() -> Booking:
    booking = Booking()
    booking.start_date = date(2025, 1, 10)
    booking.end_date = date(2025, 1, 13)
    booking.totals = {
        "days": "3",
        "rental_subtotal": "300.00",
        "renter_fee": "30.00",
        "renter_fee_base": "30.00",
        "renter_fee_gst": "0.00",
        "renter_fee_total": "30.00",
        "owner_fee": "15.00",
        "owner_fee_base": "15.00",
        "owner_fee_gst": "0.00",
        "owner_fee_total": "15.00",
        "owner_payout": "240.00",
        "platform_fee_total": "45.00",
        "damage_deposit": "150.00",
        "total_charge": "330.00",
        "gst_enabled": False,
        "gst_rate": "0.05",
        "gst_number": "",
    }
    return booking


def test_renter_full_refund_when_canceling_more_than_day_in_advance():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="renter",
        today=date(2025, 1, 8),
    )

    assert settlement.refund_to_renter == Decimal("300.00")
    assert settlement.owner_delta == Decimal("-240.00")
    assert settlement.platform_delta == Decimal("30.00")
    assert settlement.deposit_capture_amount == Decimal("0.00")
    assert settlement.deposit_release_amount == Decimal("150.00")


def test_renter_pays_one_day_penalty_within_24_hours():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="renter",
        today=date(2025, 1, 9),
    )

    assert settlement.refund_to_renter == Decimal("200.00")
    assert settlement.owner_delta == Decimal("80.00")
    assert settlement.platform_delta == Decimal("35.00")
    assert settlement.deposit_release_amount == Decimal("150.00")


def test_same_day_cancellation_keeps_half_charge_for_platform():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="renter",
        today=date(2025, 1, 10),
    )

    assert settlement.refund_to_renter == Decimal("150.00")
    assert settlement.owner_delta == Decimal("0.00")
    assert settlement.platform_delta == Decimal("180.00")
    assert settlement.deposit_release_amount == Decimal("150.00")


def test_owner_cancellation_always_full_refund():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="owner",
        today=date(2025, 1, 9),
    )

    assert settlement.refund_to_renter == Decimal("300.00")
    assert settlement.owner_delta == Decimal("-240.00")
    assert settlement.platform_delta == Decimal("30.00")
