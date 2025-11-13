from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from notifications import tasks as notification_tasks
from users.models import LoginEvent, TwoFactorChallenge

pytestmark = pytest.mark.django_db
User = get_user_model()


def spy_task(monkeypatch, task):
    calls = []

    def _capture(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(task, "delay", _capture)
    return calls


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        username="twofactor",
        email="twofactor@example.com",
        password="Secret123!",
        phone="+15551234567",
        email_verified=True,
        phone_verified=True,
    )


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


def make_challenge(user, code: str = "654321", channel: str | None = None):
    channel = channel or TwoFactorChallenge.Channel.EMAIL
    contact = user.email if channel == TwoFactorChallenge.Channel.EMAIL else user.phone
    challenge = TwoFactorChallenge.objects.create(
        user=user,
        channel=channel,
        contact=contact,
        code_hash=TwoFactorChallenge._hash_code(code),
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    challenge.set_code(code)
    challenge.save()
    return challenge, code


def test_login_without_two_factor_returns_tokens(api_client, user):
    user.two_factor_email_enabled = False
    user.two_factor_sms_enabled = False
    user.save(update_fields=["two_factor_email_enabled", "two_factor_sms_enabled"])

    resp = api_client.post(
        "/api/users/token/",
        {"username": user.username, "password": "Secret123!"},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    assert LoginEvent.objects.filter(user=user).count() == 1


def test_login_with_two_factor_email_returns_challenge_payload(api_client, user, monkeypatch):
    user.two_factor_email_enabled = True
    user.two_factor_sms_enabled = False
    user.save(update_fields=["two_factor_email_enabled", "two_factor_sms_enabled"])

    email_calls = spy_task(monkeypatch, notification_tasks.send_two_factor_code_email)
    spy_task(monkeypatch, notification_tasks.send_two_factor_code_sms)

    resp = api_client.post(
        "/api/users/token/",
        {"username": user.username, "password": "Secret123!"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["requires_2fa"] is True
    assert resp.data["channel"] == TwoFactorChallenge.Channel.EMAIL
    assert resp.data["contact_hint"] == "t***r@example.com"
    assert "challenge_id" in resp.data
    assert "resend_available_at" in resp.data
    assert "T" in resp.data["resend_available_at"]

    assert len(email_calls) == 1
    challenge = TwoFactorChallenge.objects.get(id=resp.data["challenge_id"])
    assert challenge.user == user
    assert LoginEvent.objects.filter(user=user).count() == 0


def test_two_factor_login_verify_returns_tokens_on_success(api_client, user):
    challenge, code = make_challenge(user, code="123456")
    LoginEvent.objects.all().delete()

    resp = api_client.post(
        "/api/users/two-factor/verify-login/",
        {"challenge_id": challenge.id, "code": code},
        format="json",
    )
    assert resp.status_code == 200
    assert "access" in resp.data and "refresh" in resp.data
    challenge.refresh_from_db()
    assert challenge.consumed is True
    assert LoginEvent.objects.filter(user=user).count() == 1


def test_two_factor_login_verify_blocks_invalid_codes_and_attempt_limit(api_client, user):
    challenge, _ = make_challenge(user, code="777777")

    for attempt in range(challenge.max_attempts):
        resp = api_client.post(
            "/api/users/two-factor/verify-login/",
            {"challenge_id": challenge.id, "code": "123000"},
            format="json",
        )
        assert resp.status_code == 400
        assert resp.data["code"][0] == "Invalid or expired verification code."
        challenge.refresh_from_db()
        assert challenge.attempts == attempt + 1

    resp = api_client.post(
        "/api/users/two-factor/verify-login/",
        {"challenge_id": challenge.id, "code": "123000"},
        format="json",
    )
    assert resp.status_code == 400
    challenge.refresh_from_db()
    assert challenge.attempts == challenge.max_attempts


def test_two_factor_login_resend_respects_cooldown_and_changes_code(api_client, user, monkeypatch):
    user.two_factor_email_enabled = True
    user.save(update_fields=["two_factor_email_enabled"])
    challenge, _ = make_challenge(user)

    email_calls = spy_task(monkeypatch, notification_tasks.send_two_factor_code_email)
    spy_task(monkeypatch, notification_tasks.send_two_factor_code_sms)

    resp = api_client.post(
        "/api/users/two-factor/resend-login/",
        {"challenge_id": challenge.id},
        format="json",
    )
    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0].startswith("Please wait")

    old_hash = challenge.code_hash
    challenge.last_sent_at = timezone.now() - timedelta(seconds=65)
    challenge.save(update_fields=["last_sent_at"])

    resp = api_client.post(
        "/api/users/two-factor/resend-login/",
        {"challenge_id": challenge.id},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["ok"] is True
    assert "resend_available_at" in resp.data
    assert len(email_calls) == 1

    challenge.refresh_from_db()
    assert challenge.code_hash != old_hash
    assert challenge.attempts == 0


def test_two_factor_settings_view_updates_flags_when_verified(user):
    client = auth_client(user)
    user.email_verified = True
    user.save(update_fields=["email_verified"])

    resp = client.patch(
        "/api/users/two-factor/settings/",
        {"two_factor_email_enabled": True},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["two_factor_email_enabled"] is True
    user.refresh_from_db()
    assert user.two_factor_email_enabled is True
