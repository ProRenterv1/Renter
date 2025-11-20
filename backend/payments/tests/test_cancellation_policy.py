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
        "owner_fee": "15.00",
        "owner_payout": "240.00",
        "platform_fee_total": "45.00",
        "damage_deposit": "150.00",
        "total_charge": "330.00",
    }
    return booking


def test_renter_full_refund_when_canceling_more_than_day_in_advance():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="renter",
        today=date(2025, 1, 8),
    )

    assert settlement.refund_to_renter == Decimal("330.00")
    assert settlement.owner_delta == Decimal("-240.00")
    assert settlement.platform_delta == Decimal("-45.00")
    assert settlement.deposit_capture_amount == Decimal("0.00")
    assert settlement.deposit_release_amount == Decimal("150.00")


def test_renter_pays_one_day_penalty_within_24_hours():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="renter",
        today=date(2025, 1, 9),
    )

    assert settlement.refund_to_renter == Decimal("220.00")
    assert settlement.owner_delta == Decimal("80.00")
    assert settlement.platform_delta == Decimal("15.00")
    assert settlement.deposit_release_amount == Decimal("150.00")


def test_same_day_cancellation_keeps_half_charge_for_platform():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="renter",
        today=date(2025, 1, 10),
    )

    assert settlement.refund_to_renter == Decimal("165.00")
    assert settlement.owner_delta == Decimal("0.00")
    assert settlement.platform_delta == Decimal("165.00")
    assert settlement.deposit_release_amount == Decimal("150.00")


def test_owner_cancellation_always_full_refund():
    booking = _build_paid_booking()

    settlement = compute_refund_amounts(
        booking=booking,
        actor="owner",
        today=date(2025, 1, 9),
    )

    assert settlement.refund_to_renter == Decimal("330.00")
    assert settlement.owner_delta == Decimal("-240.00")
    assert settlement.platform_delta == Decimal("-45.00")
