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
        username="operator",
        email="operator@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


@pytest.fixture
def target_user():
    return User.objects.create_user(
        username="target",
        email="target@example.com",
        phone="+1234567890",
        street_address="123 Main",
        postal_code="T0T0T0",
        password="pass123",
    )


def _authed_client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_reveal_requires_reason(target_user, operator_user):
    client = _authed_client(operator_user)
    resp = client.post(f"/api/operator/users/{target_user.id}/reveal/", {}, format="json")
    assert resp.status_code == 400


def test_reveal_returns_requested_fields(target_user, operator_user):
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/users/{target_user.id}/reveal/",
        {"reason": "review", "fields": ["email", "phone"]},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["email"] == target_user.email
    assert resp.data["phone"] == target_user.phone


def test_reveal_rejects_invalid_field(target_user, operator_user):
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/users/{target_user.id}/reveal/",
        {"reason": "review", "fields": ["email", "bogus"]},
        format="json",
    )
    assert resp.status_code == 400
