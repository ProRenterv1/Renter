from decimal import Decimal

from django.test import override_settings

from core.settings_resolver import clear_settings_cache


@override_settings(
    BOOKING_RENTER_FEE_RATE=Decimal("0.12"),
    BOOKING_OWNER_FEE_RATE=Decimal("0.04"),
    INSTANT_PAYOUT_FEE_RATE=Decimal("0.02"),
)
def test_pricing_summary_uses_current_settings(client):
    clear_settings_cache()

    response = client.get("/api/platform/pricing/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["renter_fee_bps"] == 1200
    assert payload["owner_fee_bps"] == 400
    assert payload["instant_payout_fee_bps"] == 200
    assert payload["renter_fee_rate"] == 12.0
    assert payload["owner_fee_rate"] == 4.0
    assert payload["instant_payout_fee_rate"] == 2.0
    assert payload["currency"] == "CAD"


def test_pricing_summary_prefers_operator_overrides(client, monkeypatch):
    clear_settings_cache()

    def fake_get_int(key: str, default: int) -> int:
        if key == "BOOKING_PLATFORM_FEE_BPS":
            return 850
        if key == "BOOKING_OWNER_FEE_BPS":
            return 225
        if key == "INSTANT_PAYOUT_FEE_BPS":
            return 310
        return default

    monkeypatch.setattr("core.pricing.get_int", fake_get_int)

    response = client.get("/api/platform/pricing/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["renter_fee_bps"] == 850
    assert payload["owner_fee_bps"] == 225
    assert payload["instant_payout_fee_bps"] == 310
    assert payload["renter_fee_rate"] == 8.5
    assert payload["owner_fee_rate"] == 2.25
    assert payload["instant_payout_fee_rate"] == 3.1
