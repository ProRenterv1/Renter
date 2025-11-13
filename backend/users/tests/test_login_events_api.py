import hashlib

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from users.models import LoginEvent

pytestmark = pytest.mark.django_db

User = get_user_model()


def auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "Secret123!"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def user():
    return User.objects.create_user(
        username="alice",
        email="alice@example.com",
        password="Secret123!",
    )


def create_event(user, ip, user_agent, *, is_new_device=False):
    return LoginEvent.objects.create(
        user=user,
        ip=ip,
        user_agent=user_agent,
        ua_hash=hashlib.sha256(user_agent.encode("utf-8")).hexdigest(),
        is_new_device=is_new_device,
    )


def test_login_events_are_scoped_to_authenticated_user(user):
    other = User.objects.create_user(
        username="bob",
        email="bob@example.com",
        password="Secret123!",
    )
    my_event = create_event(user, "10.0.0.1", "Chrome on Windows")
    create_event(other, "10.0.0.2", "Chrome on Windows")

    client = auth_client(user)
    resp = client.get("/api/users/login-events/")
    assert resp.status_code == 200
    returned_ids = {item["id"] for item in resp.data}
    assert my_event.id in returned_ids
    user_ids = set(LoginEvent.objects.filter(user=user).values_list("id", flat=True))
    other_ids = set(LoginEvent.objects.filter(user=other).values_list("id", flat=True))
    assert returned_ids <= user_ids
    assert not returned_ids & other_ids
    for payload in resp.data:
        assert {"id", "device", "ip", "location", "date", "is_new_device"} <= payload.keys()
        assert payload["location"] == settings.IP_GEO_PRIVATE_LABEL


def test_login_events_are_returned_newest_first(user):

    client = auth_client(user)
    resp = client.get("/api/users/login-events/?limit=5")
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.data]
    expected_ids = list(
        LoginEvent.objects.filter(user=user)
        .order_by("-created_at")
        .values_list("id", flat=True)[:5]
    )
    assert ids == expected_ids


def test_login_events_respect_limit_and_cap(user):
    for idx in range(60):
        create_event(user, f"10.0.0.{idx}", f"Firefox {idx}")

    client = auth_client(user)
    small_resp = client.get("/api/users/login-events/?limit=2")
    assert small_resp.status_code == 200
    assert len(small_resp.data) == 2

    capped_resp = client.get("/api/users/login-events/?limit=500")
    assert capped_resp.status_code == 200
    assert len(capped_resp.data) == 50
