from datetime import timedelta

import pytest
from django.utils import timezone

from operator_core.models import OperatorAuditEvent
from operator_settings.models import DbSetting, FeatureFlag, MaintenanceBanner

pytestmark = pytest.mark.django_db


def test_anon_denied_settings(ops_client):
    resp = ops_client.get("/api/operator/settings/")
    assert resp.status_code in {401, 403}


def test_normal_user_denied_settings(normal_user_ops_client):
    resp = normal_user_ops_client.get("/api/operator/settings/")
    assert resp.status_code == 403


def test_support_can_get_settings_but_cannot_put(operator_support_client):
    resp = operator_support_client.get("/api/operator/settings/")
    assert resp.status_code == 200, resp.data

    resp = operator_support_client.put(
        "/api/operator/settings/",
        {"key": "TEST_KEY", "value_type": "int", "value": 123, "reason": "test"},
        format="json",
    )
    assert resp.status_code == 403, resp.data


def test_admin_put_settings_creates_row_and_audit(operator_admin_client, operator_admin_user):
    resp = operator_admin_client.put(
        "/api/operator/settings/",
        {
            "key": "TEST_SETTING",
            "value_type": "int",
            "value": 12,
            "description": "test",
            "reason": "adjust setting",
        },
        format="json",
    )
    assert resp.status_code == 201, resp.data

    setting = DbSetting.objects.get(key="TEST_SETTING")
    assert setting.value_json == 12
    assert setting.value_type == "int"
    assert setting.updated_by == operator_admin_user

    event = OperatorAuditEvent.objects.filter(action="operator.settings.put").latest("created_at")
    assert event.entity_type == "db_setting"
    assert event.entity_id == "TEST_SETTING"
    assert event.reason == "adjust setting"


def test_settings_put_is_append_only_and_get_returns_latest(operator_admin_client):
    key = "APPEND_ONLY_KEY"
    resp1 = operator_admin_client.put(
        "/api/operator/settings/",
        {"key": key, "value_type": "int", "value": 1, "reason": "v1"},
        format="json",
    )
    assert resp1.status_code == 201, resp1.data
    resp2 = operator_admin_client.put(
        "/api/operator/settings/",
        {"key": key, "value_type": "int", "value": 2, "reason": "v2"},
        format="json",
    )
    assert resp2.status_code == 201, resp2.data

    assert DbSetting.objects.filter(key=key).count() == 2

    resp = operator_admin_client.get("/api/operator/settings/")
    assert resp.status_code == 200, resp.data
    row = next((item for item in resp.data if item["key"] == key), None)
    assert row is not None
    assert row["value_json"] == 2


def test_settings_get_ignores_future_effective_at(operator_admin_client):
    key = "EFFECTIVE_AT_KEY"
    now = timezone.now()

    resp1 = operator_admin_client.put(
        "/api/operator/settings/",
        {"key": key, "value_type": "int", "value": 1, "reason": "current"},
        format="json",
    )
    assert resp1.status_code == 201, resp1.data

    resp2 = operator_admin_client.put(
        "/api/operator/settings/",
        {
            "key": key,
            "value_type": "int",
            "value": 2,
            "effective_at": (now + timedelta(hours=1)).isoformat(),
            "reason": "future",
        },
        format="json",
    )
    assert resp2.status_code == 201, resp2.data

    resp = operator_admin_client.get("/api/operator/settings/")
    assert resp.status_code == 200, resp.data
    row = next((item for item in resp.data if item["key"] == key), None)
    assert row is not None
    assert row["value_json"] == 1


def test_settings_put_requires_reason(operator_admin_client):
    resp = operator_admin_client.put(
        "/api/operator/settings/",
        {"key": "TEST_MISSING_REASON", "value_type": "int", "value": 1},
        format="json",
    )
    assert resp.status_code == 400


def test_gst_registration_requires_number(operator_admin_client):
    resp = operator_admin_client.put(
        "/api/operator/settings/",
        {
            "key": "ORG_GST_REGISTERED",
            "value_type": "bool",
            "value": True,
            "reason": "enable gst",
        },
        format="json",
    )
    assert resp.status_code == 400, resp.data


def test_gst_number_then_enable(operator_admin_client):
    number_resp = operator_admin_client.put(
        "/api/operator/settings/",
        {
            "key": "ORG_GST_NUMBER",
            "value_type": "str",
            "value": "123456789RT0001",
            "reason": "set gst",
        },
        format="json",
    )
    assert number_resp.status_code == 201, number_resp.data

    enable_resp = operator_admin_client.put(
        "/api/operator/settings/",
        {
            "key": "ORG_GST_REGISTERED",
            "value_type": "bool",
            "value": True,
            "reason": "enable gst",
        },
        format="json",
    )
    assert enable_resp.status_code == 201, enable_resp.data


def test_support_can_get_feature_flags_but_cannot_put(operator_support_client):
    resp = operator_support_client.get("/api/operator/feature-flags/")
    assert resp.status_code == 200, resp.data

    resp = operator_support_client.put(
        "/api/operator/feature-flags/",
        {"key": "FLAG_X", "enabled": True, "reason": "test"},
        format="json",
    )
    assert resp.status_code == 403, resp.data


def test_admin_put_feature_flag_upserts_and_audits(operator_admin_client, operator_admin_user):
    resp = operator_admin_client.put(
        "/api/operator/feature-flags/",
        {"key": "FLAG_X", "enabled": True, "reason": "enable"},
        format="json",
    )
    assert resp.status_code == 200, resp.data

    flag = FeatureFlag.objects.get(key="FLAG_X")
    assert flag.enabled is True
    assert flag.updated_by == operator_admin_user

    event = OperatorAuditEvent.objects.filter(action="operator.feature_flags.put").latest(
        "created_at"
    )
    assert event.entity_type == "feature_flag"
    assert event.entity_id == "FLAG_X"
    assert event.reason == "enable"


def test_support_can_get_maintenance_but_cannot_put(operator_support_client):
    resp = operator_support_client.get("/api/operator/maintenance/")
    assert resp.status_code == 200, resp.data

    resp = operator_support_client.put(
        "/api/operator/maintenance/",
        {"enabled": True, "severity": "warning", "message": "test", "reason": "test"},
        format="json",
    )
    assert resp.status_code == 403, resp.data


def test_admin_put_maintenance_updates_and_audits(operator_admin_client, operator_admin_user):
    resp = operator_admin_client.put(
        "/api/operator/maintenance/",
        {
            "enabled": True,
            "severity": "warning",
            "message": "Maintenance soon",
            "reason": "incident",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data

    banner = MaintenanceBanner.objects.order_by("-updated_at", "-id").first()
    assert banner is not None
    assert banner.enabled is True
    assert banner.severity == "warning"
    assert banner.message == "Maintenance soon"
    assert banner.updated_by == operator_admin_user

    event = OperatorAuditEvent.objects.filter(action="operator.maintenance.put").latest(
        "created_at"
    )
    assert event.entity_type == "maintenance_banner"
    assert event.reason == "incident"
