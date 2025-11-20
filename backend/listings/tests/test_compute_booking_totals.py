"""Tests for the compute_booking_totals helper."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from listings.models import Listing
from listings.services import compute_booking_totals


def make_listing(*, daily_price: str, damage_deposit: str = "0.00") -> Listing:
    return Listing(
        owner_id=1,
        daily_price_cad=Decimal(daily_price),
        damage_deposit_cad=Decimal(damage_deposit),
    )


def test_compute_booking_totals_single_day_default_rates():
    listing = make_listing(daily_price="100.00", damage_deposit="250.00")
    totals = compute_booking_totals(
        listing=listing,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 2),
    )

    assert totals["days"] == "1"
    assert totals["rental_subtotal"] == "100.00"
    assert totals["renter_fee"] == "10.00"
    assert totals["owner_fee"] == "5.00"
    assert totals["platform_fee_total"] == "15.00"
    assert totals["owner_payout"] == "95.00"
    assert totals["damage_deposit"] == "250.00"
    assert totals["total_charge"] == "360.00"


@pytest.mark.parametrize("days", [3, 7, 30])
def test_compute_booking_totals_multi_day(days: int):
    listing = make_listing(daily_price="42.00", damage_deposit="0.00")
    start = date(2025, 2, 1)
    end = start + timedelta(days=days)

    totals = compute_booking_totals(listing=listing, start_date=start, end_date=end)

    assert totals["days"] == str(days)
    assert totals["daily_price_cad"] == "42.00"
    assert totals["rental_subtotal"] == f"{Decimal('42.00') * days:.2f}"
    renter_fee = Decimal(totals["renter_fee"])
    owner_fee = Decimal(totals["owner_fee"])
    assert Decimal(totals["platform_fee_total"]) == renter_fee + owner_fee
    assert totals["owner_payout"] == f"{(Decimal('42.00') * days) - owner_fee:.2f}"


@pytest.mark.parametrize(
    "start_date,end_date",
    [
        (date(2025, 3, 1), date(2025, 3, 1)),
        (date(2025, 3, 5), date(2025, 3, 4)),
    ],
)
def test_compute_booking_totals_invalid_ranges_raise(start_date: date, end_date: date):
    listing = make_listing(daily_price="25.00")
    with pytest.raises(ValueError):
        compute_booking_totals(listing=listing, start_date=start_date, end_date=end_date)


def test_compute_booking_totals_rounds_to_two_decimals():
    listing = make_listing(daily_price="19.99", damage_deposit="33.33")
    totals = compute_booking_totals(
        listing=listing,
        start_date=date(2025, 4, 1),
        end_date=date(2025, 4, 4),
    )

    assert totals["rental_subtotal"] == "59.97"
    assert totals["renter_fee"] == "6.00"
    assert totals["owner_fee"] == "3.00"
    assert totals["platform_fee_total"] == "9.00"
    assert totals["owner_payout"] == "56.97"
    assert totals["damage_deposit"] == "33.33"
    assert totals["total_charge"] == "99.30"
