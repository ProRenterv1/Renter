import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from listings.models import Listing

pytestmark = pytest.mark.django_db

User = get_user_model()


def auth(user):
    client = APIClient()
    token_resp = client.post(
        "/api/users/token/",
        {"username": user.username, "password": "x"},
        format="json",
    )
    token = token_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def owner_user():
    return User.objects.create_user(
        username="owner",
        password="x",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def renter_only_user():
    return User.objects.create_user(
        username="renter",
        password="x",
        can_list=False,
        can_rent=True,
    )


def create_listing_payload(**overrides):
    payload = {
        "title": "Cordless Drill",
        "description": "18V hammer drill",
        "daily_price_cad": "12.50",
        "city": "Edmonton",
    }
    payload.update(overrides)
    return payload


def test_create_listing_allowed_for_can_list(owner_user):
    client = auth(owner_user)
    resp = client.post("/api/listings/", create_listing_payload(), format="json")
    assert resp.status_code == 201
    assert resp.data["slug"]
    assert Listing.objects.filter(slug=resp.data["slug"]).exists()


def test_create_listing_forbidden_without_can_list(renter_only_user):
    client = auth(renter_only_user)
    resp = client.post(
        "/api/listings/",
        create_listing_payload(title="Nope"),
        format="json",
    )
    assert resp.status_code in (401, 403)


def test_read_and_search_public(owner_user):
    client = auth(owner_user)
    client.post(
        "/api/listings/",
        create_listing_payload(title="Ladder 12ft", daily_price_cad="7.00"),
        format="json",
    )

    anon = APIClient()
    all_resp = anon.get("/api/listings/")
    assert isinstance(all_resp.data, list) and len(all_resp.data) >= 1

    search_resp = anon.get("/api/listings/?q=Ladder&price_min=5&price_max=10")
    assert len(search_resp.data) >= 1


def test_owner_can_update_and_delete_listing(owner_user):
    client = auth(owner_user)
    create_resp = client.post("/api/listings/", create_listing_payload(), format="json")
    slug = create_resp.data["slug"]

    update_resp = client.patch(
        f"/api/listings/{slug}/",
        {"title": "Updated Drill"},
        format="json",
    )
    assert update_resp.status_code == 200
    assert update_resp.data["title"] == "Updated Drill"

    delete_resp = client.delete(f"/api/listings/{slug}/")
    assert delete_resp.status_code == 204
    assert not Listing.objects.filter(slug=slug).exists()


def test_non_owner_cannot_modify_listing(owner_user, renter_only_user):
    owner_client = auth(owner_user)
    create_resp = owner_client.post(
        "/api/listings/",
        create_listing_payload(),
        format="json",
    )
    slug = create_resp.data["slug"]

    renter_client = auth(renter_only_user)
    patch_resp = renter_client.patch(
        f"/api/listings/{slug}/",
        {"title": "Bad Update"},
        format="json",
    )
    assert patch_resp.status_code == 403

    delete_resp = renter_client.delete(f"/api/listings/{slug}/")
    assert delete_resp.status_code == 403
    assert Listing.objects.filter(slug=slug).exists()
