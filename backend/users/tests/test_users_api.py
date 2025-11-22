import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from notifications import tasks as notification_tasks
from users.models import ContactVerificationChallenge

pytestmark = pytest.mark.django_db

User = get_user_model()


def auth_client(user):
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "Secret123!"},
        format="json",
    )
    token = token_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def user():
    return User.objects.create_user(
        username="demo",
        email="demo@example.com",
        password="Secret123!",
        first_name="Demo",
        last_name="User",
        can_rent=True,
        can_list=False,
    )


def spy_task(monkeypatch, task):
    calls = []

    def _capture(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(task, "delay", _capture)
    return calls


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("get", "/api/users/login-events/", None),
        ("patch", "/api/users/two-factor/settings/", {"two_factor_email_enabled": True}),
        ("post", "/api/users/change-password/", {"current_password": "x", "new_password": "y"}),
        ("post", "/api/users/contact-verification/request/", {"channel": "email"}),
        (
            "post",
            "/api/users/contact-verification/verify/",
            {"channel": "email", "code": "000000", "challenge_id": 1},
        ),
    ],
)
def test_protected_user_endpoints_require_authentication(method, path, payload):
    client = APIClient()
    call = getattr(client, method)
    kwargs = {"format": "json"}
    if payload is not None:
        kwargs["data"] = payload
    resp = call(path, **kwargs)
    assert resp.status_code == 401


def test_signup_creates_user_and_hashes_password():
    client = APIClient()
    payload = {
        "username": "newuser",
        "email": "new@example.com",
        "password": "StrongPass123!",
        "first_name": "New",
        "last_name": "Person",
        "can_rent": True,
        "can_list": True,
    }
    resp = client.post("/api/users/signup/", payload, format="json")
    assert resp.status_code == 201
    created = User.objects.get(username="newuser")
    assert created.email == payload["email"]
    assert created.check_password(payload["password"])
    assert "password" not in resp.data


def test_signup_requires_password():
    client = APIClient()
    resp = client.post(
        "/api/users/signup/",
        {
            "username": "weakling",
            "email": "weak@example.com",
            "first_name": "Weak",
            "last_name": "Ling",
            "can_rent": True,
            "can_list": True,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert not User.objects.filter(username="weakling").exists()


def test_me_requires_authentication():
    client = APIClient()
    resp = client.get("/api/users/me/")
    assert resp.status_code == 401


def test_me_returns_profile_for_authenticated_user(user):
    client = auth_client(user)
    resp = client.get("/api/users/me/")
    assert resp.status_code == 200
    assert resp.data["username"] == user.username
    assert resp.data["email"] == user.email
    assert resp.data["street_address"] == ""
    assert resp.data["city"] == ""
    assert resp.data["province"] == ""
    assert resp.data["postal_code"] == ""


def test_me_allows_partial_update(user):
    client = auth_client(user)
    resp = client.patch(
        "/api/users/me/",
        {"first_name": "Updated", "can_list": True},
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.first_name == "Updated"
    assert user.can_list is True


def test_me_updates_address_fields(user):
    client = auth_client(user)
    payload = {
        "street_address": "123 Main St.",
        "city": "Edmonton",
        "province": "ab",
        "postal_code": "t5k-2m5",
    }
    resp = client.patch("/api/users/me/", payload, format="json")
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.street_address == "123 Main St."
    assert user.city == "Edmonton"
    assert user.province == "AB"
    assert user.postal_code == "T5K 2M5"


def test_me_rejects_invalid_postal_code(user):
    client = auth_client(user)
    resp = client.patch(
        "/api/users/me/",
        {"postal_code": "@@@@@"},
        format="json",
    )
    assert resp.status_code == 400
    assert "postal_code" in resp.data


def test_contact_verification_email_flow(user, monkeypatch):
    user.email_verified = False
    user.save(update_fields=["email_verified"])
    client = auth_client(user)

    monkeypatch.setattr(
        ContactVerificationChallenge,
        "generate_code",
        classmethod(lambda cls: "246810"),
    )
    email_calls = spy_task(monkeypatch, notification_tasks.send_contact_verification_email)

    request_resp = client.post(
        "/api/users/contact-verification/request/",
        {"channel": "email"},
        format="json",
    )
    assert request_resp.status_code == 200
    challenge_id = request_resp.data["challenge_id"]
    challenge = ContactVerificationChallenge.objects.get(id=challenge_id)
    assert challenge.contact == user.email.lower()
    assert email_calls and email_calls[0]["args"][2] == "246810"

    verify_resp = client.post(
        "/api/users/contact-verification/verify/",
        {"channel": "email", "code": "246810", "challenge_id": challenge_id},
        format="json",
    )
    assert verify_resp.status_code == 200
    user.refresh_from_db()
    assert user.email_verified is True


def test_contact_verification_phone_flow(user, monkeypatch):
    user.phone = "+15551234567"
    user.phone_verified = False
    user.save(update_fields=["phone", "phone_verified"])
    client = auth_client(user)

    monkeypatch.setattr(
        ContactVerificationChallenge,
        "generate_code",
        classmethod(lambda cls: "135790"),
    )
    sms_calls = spy_task(monkeypatch, notification_tasks.send_contact_verification_sms)

    request_resp = client.post(
        "/api/users/contact-verification/request/",
        {"channel": "phone"},
        format="json",
    )
    assert request_resp.status_code == 200
    challenge_id = request_resp.data["challenge_id"]
    assert sms_calls and sms_calls[0]["args"][2] == "135790"

    verify_resp = client.post(
        "/api/users/contact-verification/verify/",
        {"channel": "phone", "code": "135790", "challenge_id": challenge_id},
        format="json",
    )
    assert verify_resp.status_code == 200
    user.refresh_from_db()
    assert user.phone_verified is True


def test_contact_verification_respects_cooldown(user):
    client = auth_client(user)

    first = client.post(
        "/api/users/contact-verification/request/",
        {"channel": "email"},
        format="json",
    )
    assert first.status_code == 200

    second = client.post(
        "/api/users/contact-verification/request/",
        {"channel": "email"},
        format="json",
    )
    assert second.status_code == 400
    assert "non_field_errors" in second.data


def test_contact_verification_fails_if_contact_changed(user, monkeypatch):
    user.phone = "+15557654321"
    user.phone_verified = False
    user.save(update_fields=["phone", "phone_verified"])
    client = auth_client(user)

    monkeypatch.setattr(
        ContactVerificationChallenge,
        "generate_code",
        classmethod(lambda cls: "654321"),
    )

    request_resp = client.post(
        "/api/users/contact-verification/request/",
        {"channel": "phone"},
        format="json",
    )
    assert request_resp.status_code == 200
    challenge_id = request_resp.data["challenge_id"]

    # Simulate updating the phone number before verifying.
    user.phone = "+15559876543"
    user.save(update_fields=["phone"])

    verify_resp = client.post(
        "/api/users/contact-verification/verify/",
        {"channel": "phone", "code": "654321", "challenge_id": challenge_id},
        format="json",
    )
    assert verify_resp.status_code == 400
    assert "non_field_errors" in verify_resp.data


def test_phone_update_resets_verification_flag(user):
    user.phone = "+15551110000"
    user.phone_verified = True
    user.save(update_fields=["phone", "phone_verified"])
    client = auth_client(user)

    resp = client.patch(
        "/api/users/me/",
        {"phone": "+15559990000"},
        format="json",
    )
    assert resp.status_code == 200
    user.refresh_from_db()
    assert user.phone == "+15559990000"
    assert user.phone_verified is False
