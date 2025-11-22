"""Permission and creation rule tests for ListingViewSet."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from listings.models import Listing

pytestmark = pytest.mark.django_db

User = get_user_model()


def _auth_client(user):
    client = APIClient()
    resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "testpass"},
        format="json",
    )
    token = resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def listing_payload(**overrides):
    payload = {
        "title": "Cordless Drill",
        "description": "Compact hammer drill",
        "daily_price_cad": "19.99",
        "replacement_value_cad": "350.00",
        "damage_deposit_cad": "75.00",
        "city": "Edmonton",
        "postal_code": "T5K 2M5",
    }
    payload.update(overrides)
    return payload


def create_listing(owner):
    return Listing.objects.create(
        owner=owner,
        title="Published Saw",
        description="Ready to rent",
        daily_price_cad=Decimal("15.00"),
        replacement_value_cad=Decimal("250.00"),
        damage_deposit_cad=Decimal("80.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )


def test_anonymous_read_allowed(owner_user):
    listing = create_listing(owner_user)
    client = APIClient()

    list_resp = client.get("/api/listings/")
    assert list_resp.status_code == 200, list_resp.data
    slugs = {item["slug"] for item in list_resp.data["results"]}
    assert listing.slug in slugs

    detail_resp = client.get(f"/api/listings/{listing.slug}/")
    assert detail_resp.status_code == 200, detail_resp.data
    assert detail_resp.data["slug"] == listing.slug


def test_anonymous_cannot_create_listing():
    client = APIClient()
    resp = client.post("/api/listings/", listing_payload(), format="json")
    assert resp.status_code in {401, 403}
    assert Listing.objects.count() == 0


def test_authenticated_without_can_list_cannot_create(renter_user):
    client = _auth_client(renter_user)

    resp = client.post("/api/listings/", listing_payload(), format="json")

    assert resp.status_code in {400, 403}
    if resp.status_code == 400:
        assert resp.data["detail"] == "You are not allowed to create listings."
    assert Listing.objects.count() == 0


@pytest.mark.parametrize(
    ("email_verified", "phone_verified", "message"),
    [
        (False, True, "Please verify your email before creating listings."),
        (True, False, "Please verify your phone before creating listings."),
    ],
)
def test_contact_verification_required(email_verified, phone_verified, message):
    user = User.objects.create_user(
        username=f"owner-{int(email_verified)}-{int(phone_verified)}",
        password="testpass",
        can_list=True,
        can_rent=True,
        email_verified=email_verified,
        phone_verified=phone_verified,
    )
    client = _auth_client(user)

    resp = client.post("/api/listings/", listing_payload(), format="json")

    assert resp.status_code == 400
    assert resp.data["detail"] == message


def test_authenticated_can_create_listing(owner_user):
    client = _auth_client(owner_user)

    resp = client.post("/api/listings/", listing_payload(), format="json")

    assert resp.status_code == 201, resp.data
    slug = resp.data["slug"]
    assert Listing.objects.filter(slug=slug, owner=owner_user).exists()
    assert resp.data["owner"] == owner_user.id
    assert resp.data["owner_username"] == owner_user.username


def test_only_owner_can_update_listing(owner_user, other_user):
    listing = create_listing(owner_user)

    other_client = _auth_client(other_user)
    other_resp = other_client.patch(
        f"/api/listings/{listing.slug}/",
        {"title": "Attempted Update"},
        format="json",
    )
    assert other_resp.status_code in {400, 403}
    if other_resp.status_code == 400:
        assert other_resp.data["detail"] == "You do not have permission to modify this listing."

    owner_client = _auth_client(owner_user)
    owner_resp = owner_client.patch(
        f"/api/listings/{listing.slug}/",
        {"title": "Updated Title"},
        format="json",
    )
    assert owner_resp.status_code == 200, owner_resp.data
    listing.refresh_from_db()
    assert listing.title == "Updated Title"
