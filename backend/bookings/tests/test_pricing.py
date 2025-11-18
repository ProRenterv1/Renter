from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings

from listings.models import Listing
from listings.services import compute_booking_totals


def make_listing(*, daily_price: str, damage_deposit: str = "0.00") -> Listing:
    return Listing(
        owner_id=1,
        daily_price_cad=Decimal(daily_price),
        damage_deposit_cad=Decimal(damage_deposit),
    )


def test_compute_booking_totals_returns_expected_values():
    listing = make_listing(daily_price="100.00", damage_deposit="75.00")
    totals = compute_booking_totals(
        listing=listing,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 6),
    )

    assert totals["days"] == "5"
    assert totals["daily_price_cad"] == "100.00"
    assert totals["rental_subtotal"] == "500.00"
    assert totals["renter_fee"] == "50.00"
    assert totals["owner_fee"] == "25.00"
    assert totals["platform_fee_total"] == "75.00"
    assert totals["owner_payout"] == "475.00"
    assert totals["damage_deposit"] == "75.00"
    assert totals["total_charge"] == "625.00"

    # Ensure all values are serialized strings for JSON stability
    assert all(isinstance(value, str) for value in totals.values())


@pytest.mark.parametrize(
    "start_date,end_date",
    [
        (date(2024, 1, 1), date(2024, 1, 1)),
        (date(2024, 1, 5), date(2024, 1, 4)),
    ],
)
def test_compute_booking_totals_invalid_dates(start_date: date, end_date: date):
    listing = make_listing(daily_price="10.00")
    with pytest.raises(ValueError):
        compute_booking_totals(listing=listing, start_date=start_date, end_date=end_date)


@override_settings(
    BOOKING_RENTER_FEE_RATE=Decimal("0.12"),
    BOOKING_OWNER_FEE_RATE=Decimal("0.07"),
)
def test_compute_booking_totals_uses_overridden_fee_rates():
    listing = make_listing(daily_price="200.00")
    totals = compute_booking_totals(
        listing=listing,
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 4),
    )

    # Base: 3 days * 200 = 600
    assert totals["rental_subtotal"] == "600.00"
    # Renter fee: 12%
    assert totals["renter_fee"] == "72.00"
    # Owner fee: 7%
    assert totals["owner_fee"] == "42.00"
    # Owner payout: base - owner fee
    assert totals["owner_payout"] == "558.00"
