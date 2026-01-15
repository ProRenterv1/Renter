from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings

from core.settings_resolver import clear_settings_cache
from listings.models import Listing
from listings.services import compute_booking_totals
from operator_settings.models import DbSetting


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
    assert totals["renter_fee_total"] == "50.00"
    assert totals["owner_fee"] == "25.00"
    assert totals["owner_fee_total"] == "25.00"
    assert totals["platform_fee_total"] == "75.00"
    assert totals["owner_payout"] == "475.00"
    assert totals["damage_deposit"] == "75.00"
    assert totals["total_charge"] == "625.00"

    assert totals["gst_enabled"] is False
    assert totals["gst_rate"] == "0.05"
    assert totals["gst_number"] == ""
    assert all(isinstance(value, str) for key, value in totals.items() if key != "gst_enabled")


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
    assert totals["renter_fee_total"] == "72.00"
    # Owner fee: 7%
    assert totals["owner_fee"] == "42.00"
    assert totals["owner_fee_total"] == "42.00"
    # Owner payout: base - owner fee
    assert totals["owner_payout"] == "558.00"


def test_compute_booking_totals_all_fee_overrides_to_zero():
    listing = make_listing(daily_price="120.00")
    totals = compute_booking_totals(
        listing=listing,
        start_date=date(2024, 7, 1),
        end_date=date(2024, 7, 3),
        renter_fee_bps_override=0,
        owner_fee_bps_override=0,
    )

    assert totals["rental_subtotal"] == "240.00"
    assert totals["renter_fee"] == "0.00"
    assert totals["renter_fee_total"] == "0.00"
    assert totals["owner_fee"] == "0.00"
    assert totals["owner_fee_total"] == "0.00"
    assert totals["platform_fee_total"] == "0.00"
    assert totals["owner_payout"] == "240.00"


@pytest.mark.django_db
def test_compute_booking_totals_with_gst_enabled():
    DbSetting.objects.create(
        key="ORG_GST_NUMBER",
        value_json="123456789RT0001",
        value_type="str",
    )
    DbSetting.objects.create(
        key="ORG_GST_REGISTERED",
        value_json=True,
        value_type="bool",
    )
    clear_settings_cache()

    listing = make_listing(daily_price="50.00")
    totals = compute_booking_totals(
        listing=listing,
        start_date=date(2024, 8, 1),
        end_date=date(2024, 8, 3),
    )

    assert totals["rental_subtotal"] == "100.00"
    assert totals["renter_fee_base"] == "10.00"
    assert totals["renter_fee_gst"] == "0.50"
    assert totals["renter_fee_total"] == "10.50"
    assert totals["owner_fee_base"] == "5.00"
    assert totals["owner_fee_gst"] == "0.25"
    assert totals["owner_fee_total"] == "5.25"
    assert totals["platform_fee_total"] == "15.75"
    assert totals["owner_payout"] == "94.75"
    assert totals["total_charge"] == "110.50"
    assert totals["gst_enabled"] is True
