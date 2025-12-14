import importlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from rest_framework.test import APIClient

import renter.urls as renter_urls
from operator_core.models import OperatorAuditEvent
from operator_users.models import UserRiskFlag

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def enable_operator_routes(settings):
    original_enable = settings.ENABLE_OPERATOR
    original_hosts = getattr(settings, "OPS_ALLOWED_HOSTS", [])
    original_allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))

    settings.ENABLE_OPERATOR = True
    settings.OPS_ALLOWED_HOSTS = ["ops.example.com"]
    settings.ALLOWED_HOSTS = ["ops.example.com", "public.example.com", "testserver"]
    clear_url_caches()
    importlib.reload(renter_urls)
    yield
    settings.ENABLE_OPERATOR = original_enable
    settings.OPS_ALLOWED_HOSTS = original_hosts
    settings.ALLOWED_HOSTS = original_allowed_hosts
    clear_url_caches()
    importlib.reload(renter_urls)


@pytest.fixture
def operator_user():
    group, _ = Group.objects.get_or_create(name="operator_admin")
    user = User.objects.create_user(
        username="op-admin",
        email="admin@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def target_user():
    return User.objects.create_user(
        username="target-user",
        email="target@example.com",
        password="pass123",
        can_rent=True,
        can_list=True,
    )


def _authed_client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_suspend_and_reinstate(operator_user, target_user):
    client = _authed_client(operator_user)

    resp = client.post(
        f"/api/operator/users/{target_user.id}/suspend/",
        {"reason": "policy violation"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    target_user.refresh_from_db()
    assert target_user.is_active is False
    suspend_event = OperatorAuditEvent.objects.filter(action="operator.user.suspend").latest(
        "created_at"
    )
    assert suspend_event.entity_type == OperatorAuditEvent.EntityType.USER
    assert suspend_event.entity_id == str(target_user.id)
    assert suspend_event.reason == "policy violation"

    resp = client.post(
        f"/api/operator/users/{target_user.id}/reinstate/",
        {"reason": "review cleared"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    target_user.refresh_from_db()
    assert target_user.is_active is True
    reinstate_event = OperatorAuditEvent.objects.filter(action="operator.user.reinstate").latest(
        "created_at"
    )
    assert reinstate_event.entity_type == OperatorAuditEvent.EntityType.USER
    assert reinstate_event.entity_id == str(target_user.id)
    assert reinstate_event.reason == "review cleared"


def test_set_restrictions(operator_user, target_user):
    client = _authed_client(operator_user)
    payload = {"can_rent": False, "can_list": False, "reason": "limit account"}

    resp = client.post(
        f"/api/operator/users/{target_user.id}/set-restrictions/",
        payload,
        format="json",
    )

    assert resp.status_code == 200, resp.data
    target_user.refresh_from_db()
    assert target_user.can_rent is False
    assert target_user.can_list is False
    event = OperatorAuditEvent.objects.filter(action="operator.user.set_restrictions").latest(
        "created_at"
    )
    assert event.entity_type == OperatorAuditEvent.EntityType.USER
    assert event.entity_id == str(target_user.id)
    assert event.reason == "limit account"
    assert event.after_json["can_rent"] is False
    assert event.after_json["can_list"] is False


def test_mark_suspicious_creates_risk_flag_and_audit(operator_user, target_user):
    client = _authed_client(operator_user)

    resp = client.post(
        f"/api/operator/users/{target_user.id}/mark-suspicious/",
        {
            "level": UserRiskFlag.Level.HIGH,
            "category": UserRiskFlag.Category.FRAUD,
            "note": "chargeback pattern",
            "reason": "fraud review",
        },
        format="json",
    )
    assert resp.status_code == 200, resp.data
    flag_id = resp.data["risk_flag_id"]

    flag = UserRiskFlag.objects.get(id=flag_id)
    assert flag.user == target_user
    assert flag.active is True
    assert flag.created_by == operator_user

    event = OperatorAuditEvent.objects.filter(action="operator.user.mark_suspicious").latest(
        "created_at"
    )
    assert event.entity_type == OperatorAuditEvent.EntityType.USER
    assert event.entity_id == str(target_user.id)
    assert event.after_json["risk_flag_id"] == flag_id
    assert event.after_json["level"] == UserRiskFlag.Level.HIGH
    assert event.after_json["category"] == UserRiskFlag.Category.FRAUD
