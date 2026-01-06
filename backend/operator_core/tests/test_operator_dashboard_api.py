import importlib

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from rest_framework.test import APIClient

import renter.urls as renter_urls

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
    group, _ = Group.objects.get_or_create(name="operator_support")
    user = User.objects.create_user(
        username="dashboard-op",
        email="dash@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


def _authed_client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_operator_dashboard_requires_auth():
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"

    resp = client.get("/api/operator/dashboard/")

    assert resp.status_code in (401, 403)


def test_operator_dashboard_returns_expected_keys(operator_user):
    client = _authed_client(operator_user)

    resp = client.get("/api/operator/dashboard/")

    assert resp.status_code == 200, resp.data
    data = resp.data
    assert "today" in data
    assert "last_7d" in data
    assert "risk" in data
    assert "open_disputes_count" in data
    assert "rebuttals_due_soon_count" in data
