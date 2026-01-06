from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from core.settings_resolver import get_bool, get_decimal, get_int, get_setting
from operator_settings.models import DbSetting

pytestmark = pytest.mark.django_db


def test_get_setting_ignores_future_effective_at(db_setting_factory):
    db_setting_factory(
        key="FUTURE_KEY",
        value_json=123,
        value_type="int",
        effective_at=timezone.now() + timedelta(hours=1),
    )
    assert get_setting("FUTURE_KEY", "default") == "default"
    assert get_int("FUTURE_KEY", 7) == 7


def test_get_setting_picks_latest_effective_row(db_setting_factory):
    now = timezone.now()
    db_setting_factory(
        key="EFFECTIVE_KEY",
        value_json=1,
        value_type="int",
        effective_at=now - timedelta(days=2),
    )
    db_setting_factory(
        key="EFFECTIVE_KEY",
        value_json=2,
        value_type="int",
        effective_at=now - timedelta(hours=1),
    )
    assert get_int("EFFECTIVE_KEY", 0) == 2


def test_get_setting_when_all_effective_at_null_latest_updated_wins(db_setting_factory):
    older = db_setting_factory(key="NULL_EFF", value_json=1, value_type="int")
    DbSetting.objects.filter(pk=older.pk).update(updated_at=timezone.now() - timedelta(hours=1))
    db_setting_factory(key="NULL_EFF", value_json=2, value_type="int")

    assert get_int("NULL_EFF", 0) == 2


def test_typed_helpers_fallback_on_wrong_types(db_setting_factory):
    db_setting_factory(key="INT_KEY", value_json="not-an-int", value_type="int")
    db_setting_factory(key="BOOL_KEY", value_json="true", value_type="bool")
    db_setting_factory(key="DEC_KEY_BAD", value_json="not-a-decimal", value_type="decimal")
    db_setting_factory(key="DEC_KEY_OK", value_json="12.34", value_type="decimal")

    assert get_int("INT_KEY", 9) == 9
    assert get_bool("BOOL_KEY", default=False) is False
    assert get_decimal("DEC_KEY_BAD", default=Decimal("1.23")) == Decimal("1.23")
    assert get_decimal("DEC_KEY_OK", default=Decimal("0")) == Decimal("12.34")


def test_settings_resolver_cache_avoids_duplicate_queries(
    db_setting_factory, django_assert_num_queries
):
    db_setting_factory(key="CACHE_KEY", value_json=1, value_type="int")

    with django_assert_num_queries(1):
        assert get_int("CACHE_KEY", 0) == 1
        assert get_int("CACHE_KEY", 0) == 1
