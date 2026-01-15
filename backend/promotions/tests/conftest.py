import pytest

from core.settings_resolver import clear_settings_cache
from operator_settings.models import DbSetting


@pytest.fixture(autouse=True)
def _enable_platform_gst():
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
    yield
    clear_settings_cache()
