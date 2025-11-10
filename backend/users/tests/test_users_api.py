import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

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
