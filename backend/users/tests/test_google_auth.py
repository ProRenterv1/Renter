import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from users import serializers as user_serializers
from users.models import SocialIdentity

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def google_client_id(settings):
    settings.GOOGLE_OAUTH_CLIENT_ID = "google-client-id"
    return settings.GOOGLE_OAUTH_CLIENT_ID


def _mock_google_verify(monkeypatch, payload):
    def _fake_verify(token, request, audience=None):
        return payload

    monkeypatch.setattr(user_serializers.google_id_token, "verify_oauth2_token", _fake_verify)


def test_google_login_existing_identity(api_client, google_client_id, monkeypatch):
    user = User.objects.create_user(
        username="google-user",
        email="google@example.com",
        password="Secret123!",
    )
    SocialIdentity.objects.create(
        user=user,
        provider=SocialIdentity.Provider.GOOGLE,
        provider_user_id="sub-123",
        email="google@example.com",
    )

    _mock_google_verify(
        monkeypatch,
        {
            "sub": "sub-123",
            "email": "google@example.com",
            "email_verified": True,
            "iss": "accounts.google.com",
        },
    )

    resp = api_client.post(
        "/api/users/google/",
        {"id_token": "token"},
        format="json",
    )

    assert resp.status_code == 200
    assert "access" in resp.data


def test_google_login_links_verified_email(api_client, google_client_id, monkeypatch):
    user = User.objects.create_user(
        username="verified-user",
        email="linked@example.com",
        password="Secret123!",
    )
    user.email_verified = True
    user.save(update_fields=["email_verified"])

    _mock_google_verify(
        monkeypatch,
        {
            "sub": "sub-456",
            "email": "linked@example.com",
            "email_verified": True,
            "iss": "accounts.google.com",
        },
    )

    resp = api_client.post(
        "/api/users/google/",
        {"id_token": "token"},
        format="json",
    )

    assert resp.status_code == 200
    assert SocialIdentity.objects.filter(
        user=user,
        provider=SocialIdentity.Provider.GOOGLE,
        provider_user_id="sub-456",
    ).exists()


def test_google_login_rejects_unverified_existing_email(api_client, google_client_id, monkeypatch):
    user = User.objects.create_user(
        username="unverified-user",
        email="unverified@example.com",
        password="Secret123!",
    )
    user.email_verified = False
    user.save(update_fields=["email_verified"])

    _mock_google_verify(
        monkeypatch,
        {
            "sub": "sub-789",
            "email": "unverified@example.com",
            "email_verified": True,
            "iss": "accounts.google.com",
        },
    )

    resp = api_client.post(
        "/api/users/google/",
        {"id_token": "token"},
        format="json",
    )

    assert resp.status_code == 400
    assert resp.data["detail"] == "Email exists but is not verified."


def test_google_login_creates_new_user(api_client, google_client_id, monkeypatch):
    _mock_google_verify(
        monkeypatch,
        {
            "sub": "sub-new",
            "email": "newgoogle@example.com",
            "email_verified": True,
            "iss": "accounts.google.com",
            "given_name": "New",
            "family_name": "User",
        },
    )

    resp = api_client.post(
        "/api/users/google/",
        {"id_token": "token"},
        format="json",
    )

    assert resp.status_code == 200
    user = User.objects.get(email="newgoogle@example.com")
    assert user.email_verified is True
    assert user.has_usable_password() is False
    assert SocialIdentity.objects.filter(
        user=user,
        provider=SocialIdentity.Provider.GOOGLE,
        provider_user_id="sub-new",
    ).exists()
