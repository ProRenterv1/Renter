from decimal import Decimal

import pytest

from core.settings_resolver import clear_settings_cache
from operator_settings.models import DbSetting
from payments.tax import compute_fee_with_gst, split_tax_included

pytestmark = pytest.mark.django_db


def test_compute_fee_with_gst_disabled():
    clear_settings_cache()
    base, gst, total = compute_fee_with_gst(Decimal("10.00"))
    assert base == Decimal("10.00")
    assert gst == Decimal("0.00")
    assert total == Decimal("10.00")


def test_compute_fee_with_gst_enabled():
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
    base, gst, total = compute_fee_with_gst(Decimal("10.00"))
    assert base == Decimal("10.00")
    assert gst == Decimal("0.50")
    assert total == Decimal("10.50")


def test_split_tax_included():
    base, gst = split_tax_included(Decimal("10.00"), Decimal("0.05"))
    assert base == Decimal("9.52")
    assert gst == Decimal("0.48")
