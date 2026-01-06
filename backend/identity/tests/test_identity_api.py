"""Tests for the identity verification API endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from identity.models import is_user_identity_verified
from payments.models import OwnerPayoutAccount

pytestmark = pytest.mark.django_db


def auth_client(user):
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = token_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def test_identity_endpoints_require_authentication():
    client = APIClient()
    start_resp = client.post("/api/identity/start/")
    status_resp = client.get("/api/identity/status/")
    assert start_resp.status_code == 401
    assert status_resp.status_code == 401


def test_identity_start_returns_connect_message(renter_user):
    OwnerPayoutAccount.objects.filter(user=renter_user).delete()
    client = auth_client(renter_user)
    resp = client.post("/api/identity/start/")

    assert resp.status_code == 400
    assert "Connect onboarding" in resp.data["detail"]
    assert resp.data["already_verified"] is False


def test_identity_status_uses_connect_account(renter_user):
    OwnerPayoutAccount.objects.filter(user=renter_user).delete()
    client = auth_client(renter_user)

    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is False
    assert resp.data["latest"] is None

    OwnerPayoutAccount.objects.create(
        user=renter_user,
        stripe_account_id="acct_identity_123",
        is_fully_onboarded=True,
        charges_enabled=True,
        payouts_enabled=True,
    )

    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is True
    assert resp.data["latest"]["status"] == "verified"
    assert resp.data["latest"]["session_id"] == "acct_identity_123"
    renter_user.refresh_from_db()
    assert is_user_identity_verified(renter_user) is True
