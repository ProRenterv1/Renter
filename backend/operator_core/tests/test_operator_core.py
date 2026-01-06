import importlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from rest_framework.test import APIClient

import renter.urls as renter_urls
from operator_core.models import OperatorAuditEvent

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


def test_operator_routes_404_on_public_host():
    client = APIClient()
    client.defaults["HTTP_HOST"] = "public.example.com"

    resp = client.get("/api/operator/me/")

    assert resp.status_code == 404


def test_operator_me_requires_staff():
    user = User.objects.create_user(username="op-user", email="op@example.com", password="pass123")
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)

    resp = client.get("/api/operator/me/")

    assert resp.status_code == 403


def test_operator_audit_test_requires_admin_role():
    user = User.objects.create_user(
        username="op-nonadmin",
        email="nonadmin@example.com",
        password="pass123",
        is_staff=True,
    )
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)

    resp = client.post("/api/operator/audit-test/", {"reason": "check"}, format="json")

    assert resp.status_code == 403
    assert OperatorAuditEvent.objects.count() == 0


def test_operator_audit_test_creates_event_for_admin():
    admin_group, _ = Group.objects.get_or_create(name="operator_admin")
    user = User.objects.create_user(
        username="op-admin",
        email="admin@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(admin_group)

    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)

    resp = client.post(
        "/api/operator/audit-test/",
        {"reason": "testing audit hook"},
        format="json",
        HTTP_USER_AGENT="pytest",
    )

    assert resp.status_code == 201, resp.data
    event_id = resp.data["audit_event_id"]
    event = OperatorAuditEvent.objects.get(id=event_id)
    assert resp.data["ok"] is True
    assert event.actor == user
    assert event.reason == "testing audit hook"
    assert event.action == "operator.audit_test"
    assert event.entity_type == "dispute_case"
