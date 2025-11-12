import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from notifications import tasks as notification_tasks
from users.models import LoginEvent, PasswordResetChallenge

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture(autouse=True)
def _email_backend(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    return settings


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def user():
    return User.objects.create_user(
        username="demo",
        email="demo@example.com",
        password="Secret123!",
        phone="+15551234567",
        first_name="Demo",
        last_name="User",
    )


def spy_task(monkeypatch, task):
    """Patch task.delay to record invocations."""
    calls = []

    def _capture(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(task, "delay", _capture)
    return calls


def _obtain_token(client, identifier, password):
    resp = client.post(
        "/api/users/token/",
        {"identifier": identifier, "password": password},
        format="json",
    )
    assert resp.status_code == 200
    return resp.data["access"]


def test_signup_with_email_and_login_success(api_client):
    payload = {
        "username": "newuser",
        "email": "new@example.com",
        "password": "StrongPass123!",
        "first_name": "New",
        "last_name": "Person",
        "can_rent": True,
        "can_list": True,
    }
    create_resp = api_client.post("/api/users/signup/", payload, format="json")
    assert create_resp.status_code == 201

    token_resp = api_client.post(
        "/api/users/token/",
        {"identifier": payload["email"], "password": payload["password"]},
        format="json",
    )
    assert token_resp.status_code == 200
    assert "access" in token_resp.data


def test_signup_with_phone_and_login_success(api_client):
    payload = {
        "username": "phoneuser",
        "phone": "5553331122",
        "password": "StrongPass123!",
        "first_name": "Phone",
        "last_name": "User",
        "can_rent": True,
        "can_list": False,
    }
    resp = api_client.post("/api/users/signup/", payload, format="json")
    assert resp.status_code == 201

    # Phone should be normalized to +1 prefix.
    normalized_phone = User.objects.get(username="phoneuser").phone
    assert normalized_phone.endswith(payload["phone"])

    token_resp = api_client.post(
        "/api/users/token/",
        {"identifier": payload["phone"], "password": payload["password"]},
        format="json",
    )
    assert token_resp.status_code == 200
    assert "access" in token_resp.data


def test_login_records_login_event_and_triggers_alert_on_new_device(api_client, user, monkeypatch):
    email_calls = spy_task(monkeypatch, notification_tasks.send_login_alert_email)
    sms_calls = spy_task(monkeypatch, notification_tasks.send_login_alert_sms)

    resp = api_client.post(
        "/api/users/token/",
        {"identifier": user.email, "password": "Secret123!"},
        format="json",
        HTTP_X_FORWARDED_FOR="203.0.113.10",
        HTTP_USER_AGENT="AuthTest/1.0",
    )
    assert resp.status_code == 200

    event = LoginEvent.objects.get(user=user)
    assert event.ip == "203.0.113.10"
    assert event.user_agent == "AuthTest/1.0"
    assert event.is_new_device is True
    user.refresh_from_db()
    assert user.last_login_ip == "203.0.113.10"
    assert user.last_login_ua == "AuthTest/1.0"
    assert email_calls
    assert sms_calls


def test_password_reset_email_flow_happy_path(api_client, user, monkeypatch):
    monkeypatch.setattr(PasswordResetChallenge, "generate_code", classmethod(lambda cls: "321654"))
    code_calls = spy_task(monkeypatch, notification_tasks.send_password_reset_code_email)
    changed_email_calls = spy_task(monkeypatch, notification_tasks.send_password_changed_email)

    request_resp = api_client.post(
        "/api/users/password-reset/request/",
        {"contact": user.email},
        format="json",
    )
    assert request_resp.status_code == 200
    challenge = PasswordResetChallenge.objects.get(user=user, channel="email")
    assert code_calls and code_calls[0]["args"][2] == "321654"

    verify_resp = api_client.post(
        "/api/users/password-reset/verify/",
        {"challenge_id": challenge.id, "code": "321654"},
        format="json",
    )
    assert verify_resp.status_code == 200
    assert verify_resp.data["verified"] is True

    complete_resp = api_client.post(
        "/api/users/password-reset/complete/",
        {"challenge_id": challenge.id, "code": "321654", "new_password": "FreshPass123!"},
        format="json",
    )
    assert complete_resp.status_code == 200
    assert complete_resp.data["ok"] is True
    assert changed_email_calls

    # User can log in with the new password.
    login_resp = api_client.post(
        "/api/users/token/",
        {"identifier": user.email, "password": "FreshPass123!"},
        format="json",
    )
    assert login_resp.status_code == 200
    assert "access" in login_resp.data


def test_password_reset_rejects_bad_code_and_limits_attempts(api_client, user, monkeypatch):
    monkeypatch.setattr(PasswordResetChallenge, "generate_code", classmethod(lambda cls: "987654"))
    spy_task(monkeypatch, notification_tasks.send_password_reset_code_email)

    api_client.post(
        "/api/users/password-reset/request/",
        {"contact": user.email},
        format="json",
    )
    challenge = PasswordResetChallenge.objects.get(user=user, channel="email")

    for _ in range(challenge.max_attempts):
        resp = api_client.post(
            "/api/users/password-reset/verify/",
            {"challenge_id": challenge.id, "code": "000000"},
            format="json",
        )
        assert resp.status_code == 400

    # Even the correct code should now fail due to attempt limit.
    resp = api_client.post(
        "/api/users/password-reset/verify/",
        {"challenge_id": challenge.id, "code": "987654"},
        format="json",
    )
    assert resp.status_code == 400


def test_password_reset_sms_flow_happy_path(api_client, user, monkeypatch):
    # Ensure a phone-only scenario.
    user.email = ""
    user.phone = "+15551230000"
    user.save(update_fields=["email", "phone"])

    monkeypatch.setattr(PasswordResetChallenge, "generate_code", classmethod(lambda cls: "111222"))
    code_calls = spy_task(monkeypatch, notification_tasks.send_password_reset_code_sms)
    changed_sms_calls = spy_task(monkeypatch, notification_tasks.send_password_changed_sms)

    request_resp = api_client.post(
        "/api/users/password-reset/request/",
        {"contact": "5551230000"},
        format="json",
    )
    assert request_resp.status_code == 200
    challenge = PasswordResetChallenge.objects.get(user=user, channel="sms")
    assert code_calls and code_calls[0]["args"][2] == "111222"

    verify_resp = api_client.post(
        "/api/users/password-reset/verify/",
        {"challenge_id": challenge.id, "code": "111222"},
        format="json",
    )
    assert verify_resp.status_code == 200

    complete_resp = api_client.post(
        "/api/users/password-reset/complete/",
        {"challenge_id": challenge.id, "code": "111222", "new_password": "SMSPass999!"},
        format="json",
    )
    assert complete_resp.status_code == 200
    assert changed_sms_calls

    login_resp = api_client.post(
        "/api/users/token/",
        {"identifier": user.phone, "password": "SMSPass999!"},
        format="json",
    )
    assert login_resp.status_code == 200
