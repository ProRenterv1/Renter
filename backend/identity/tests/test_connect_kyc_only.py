from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from identity.models import is_user_identity_verified
from payments.models import OwnerPayoutAccount

pytestmark = pytest.mark.django_db

User = get_user_model()


def _auth_client(user: User) -> APIClient:
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = token_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def _create_user(username: str) -> User:
    return User.objects.create_user(
        username=username,
        password="testpass",
        email=f"{username}@example.com",
        can_list=True,
        can_rent=True,
    )


def test_identity_verified_when_connect_onboarded(settings):
    user = _create_user("connect-verified")
    OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_verified_123",
        is_fully_onboarded=True,
        charges_enabled=True,
        payouts_enabled=True,
        last_synced_at=timezone.now(),
    )

    client = _auth_client(user)
    resp = client.get("/api/identity/status/")

    assert resp.status_code == 200, resp.data
    assert resp.data["verified"] is True
    latest = resp.data["latest"]
    assert latest["status"] == "verified"
    assert latest["session_id"] == "acct_verified_123"
    assert latest["verified_at"] is not None
    assert is_user_identity_verified(user) is True


def test_identity_pending_until_onboarded():
    user = _create_user("connect-pending")
    OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id="acct_pending_123",
        is_fully_onboarded=False,
        charges_enabled=False,
        payouts_enabled=False,
        last_synced_at=timezone.now(),
    )

    client = _auth_client(user)
    resp = client.get("/api/identity/status/")

    assert resp.status_code == 200
    assert resp.data["verified"] is False
    assert resp.data["latest"]["status"] == "pending"
    assert resp.data["latest"]["session_id"] == "acct_pending_123"
    assert resp.data["latest"]["verified_at"] is None
    assert is_user_identity_verified(user) is False


def test_identity_status_without_connect_account():
    user = _create_user("connect-none")
    client = _auth_client(user)

    resp = client.get("/api/identity/status/")

    assert resp.status_code == 200
    assert resp.data["verified"] is False
    assert resp.data["latest"] is None
    assert is_user_identity_verified(user) is False


def test_identity_start_is_disabled():
    user = _create_user("connect-start")
    client = _auth_client(user)

    resp = client.post("/api/identity/start/")

    assert resp.status_code == 400
    assert "Connect onboarding" in resp.data["detail"]
    assert resp.data["already_verified"] is False
