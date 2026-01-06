import importlib
from datetime import date, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from rest_framework.test import APIClient

import renter.urls as renter_urls
from bookings.models import Booking
from listings.models import Listing

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


def _authed_client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_operator_users_list_requires_auth():
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"

    resp = client.get("/api/operator/users/")

    assert resp.status_code in (401, 403)


def test_operator_users_list_allows_operator(operator_user):
    client = _authed_client(operator_user)
    resp = client.get("/api/operator/users/")

    assert resp.status_code == 200


def test_operator_users_list_filter_email(operator_user):
    User.objects.create_user(
        username="match",
        email="match@example.com",
        password="pass123",
        is_staff=True,
    )
    User.objects.create_user(
        username="miss",
        email="nomatch@example.com",
        password="pass123",
        is_staff=True,
    )

    client = _authed_client(operator_user)
    resp = client.get("/api/operator/users/?email=match@example.com")

    assert resp.status_code == 200
    payload = (
        resp.data["results"]
        if isinstance(resp.data, dict) and "results" in resp.data
        else resp.data
    )
    assert len(payload) == 1
    assert payload[0]["email"] == "match@example.com"


def test_operator_user_detail_includes_flags_and_counts(operator_user):
    target = User.objects.create_user(
        username="staff-target",
        email="detail@example.com",
        phone="+1234567890",
        password="pass123",
        is_staff=True,
        email_verified=True,
        phone_verified=True,
    )
    listing_owner = target
    listing = Listing.objects.create(
        owner=listing_owner,
        title="Saw",
        description="desc",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        postal_code="T0T0T0",
    )
    other_user = User.objects.create_user(
        username="renter",
        email="renter@example.com",
        password="pass123",
    )
    Booking.objects.create(
        listing=listing,
        owner=listing_owner,
        renter=other_user,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=2),
    )
    other_listing = Listing.objects.create(
        owner=other_user,
        title="Drill",
        description="desc",
        daily_price_cad="15.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        postal_code="T0T0T1",
    )
    Booking.objects.create(
        listing=other_listing,
        owner=other_user,
        renter=target,
        start_date=date.today(),
        end_date=date.today() + timedelta(days=1),
    )

    client = _authed_client(operator_user)
    resp = client.get(f"/api/operator/users/{target.id}/")

    assert resp.status_code == 200, resp.data
    assert resp.data["email_verified"] is True
    assert resp.data["phone_verified"] is True
    assert "identity_verified" in resp.data
    assert resp.data["listings_count"] == 1
    assert resp.data["bookings_as_owner_count"] == 1
    assert resp.data["bookings_as_renter_count"] == 1
