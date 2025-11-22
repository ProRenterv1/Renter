"""Tests for the identity verification API endpoints."""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from identity import api as identity_api
from identity.models import IdentityVerification

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


def test_identity_start_creates_verification_session(monkeypatch, renter_user, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_identity"
    captured = {}

    def fake_create(**kwargs):
        captured["payload"] = kwargs
        return {
            "id": "vs_test_123",
            "client_secret": "cs_test_123",
            "status": "requires_input",
        }

    monkeypatch.setattr(
        identity_api.stripe.identity.VerificationSession,
        "create",
        staticmethod(fake_create),
    )

    client = auth_client(renter_user)
    resp = client.post("/api/identity/start/")

    assert resp.status_code == 200, resp.data
    assert resp.data["session_id"] == "vs_test_123"
    assert resp.data["client_secret"] == "cs_test_123"
    assert captured["payload"]["metadata"]["user_id"] == str(renter_user.id)
    verification = IdentityVerification.objects.get(session_id="vs_test_123")
    assert verification.user_id == renter_user.id
    assert verification.status == IdentityVerification.Status.PENDING


def test_identity_status_reflects_verification(renter_user):
    IdentityVerification.objects.filter(user=renter_user).delete()
    client = auth_client(renter_user)

    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is False
    assert resp.data["latest"] is None

    verification = IdentityVerification.objects.create(
        user=renter_user,
        session_id="vs_verified",
        status=IdentityVerification.Status.VERIFIED,
        verified_at=timezone.now(),
    )

    resp = client.get("/api/identity/status/")
    assert resp.status_code == 200
    assert resp.data["verified"] is True
    assert resp.data["latest"]["status"] == IdentityVerification.Status.VERIFIED
    assert resp.data["latest"]["session_id"] == "vs_verified"
    assert resp.data["latest"]["verified_at"] == verification.verified_at.isoformat()
