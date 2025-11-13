from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from listings.models import Category, Listing

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


@pytest.fixture
def other_user():
    return User.objects.create_user(
        username="other",
        password="x",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def category():
    return Category.objects.create(name="Tools")


def create_listing_payload(**overrides):
    payload = {
        "title": "Cordless Drill",
        "description": "18V hammer drill",
        "daily_price_cad": "12.50",
        "replacement_value_cad": "200.00",
        "damage_deposit_cad": "50.00",
        "city": "Edmonton",
    }
    payload.update(overrides)
    return payload


def make_listing(owner, **overrides):
    data = {
        "owner": owner,
        "title": "Sample Listing",
        "description": "Sample description",
        "daily_price_cad": Decimal("25.00"),
        "replacement_value_cad": Decimal("200.00"),
        "damage_deposit_cad": Decimal("50.00"),
        "city": "Edmonton",
        "is_active": True,
        "is_available": True,
    }
    data.update(overrides)
    return Listing.objects.create(**data)


def test_create_listing_success(owner_user, category):
    client = auth(owner_user)
    payload = create_listing_payload(category=category.slug)
    resp = client.post("/api/listings/", payload, format="json")
    assert resp.status_code == 201
    assert resp.data["owner"] == owner_user.id
    assert resp.data["daily_price_cad"] == payload["daily_price_cad"]
    assert resp.data["replacement_value_cad"] == payload["replacement_value_cad"]
    assert resp.data["damage_deposit_cad"] == payload["damage_deposit_cad"]
    assert resp.data["is_available"] is True
    assert resp.data["category_name"] == category.name
    assert Listing.objects.filter(slug=resp.data["slug"]).exists()


def test_create_listing_requires_positive_price(owner_user):
    client = auth(owner_user)
    resp = client.post(
        "/api/listings/",
        create_listing_payload(daily_price_cad="0"),
        format="json",
    )
    assert resp.status_code == 400
    assert "greater than or equal" in str(resp.data["daily_price_cad"][0])


def test_create_listing_requires_non_negative_replacement_value(owner_user):
    client = auth(owner_user)
    resp = client.post(
        "/api/listings/",
        create_listing_payload(replacement_value_cad="-1"),
        format="json",
    )
    assert resp.status_code == 400
    assert "greater than or equal" in str(resp.data["replacement_value_cad"][0])


def test_create_listing_requires_non_negative_damage_deposit(owner_user):
    client = auth(owner_user)
    resp = client.post(
        "/api/listings/",
        create_listing_payload(damage_deposit_cad="-0.50"),
        format="json",
    )
    assert resp.status_code == 400
    assert "greater than or equal" in str(resp.data["damage_deposit_cad"][0])


def test_create_listing_requires_authentication(category):
    client = APIClient()
    resp = client.post(
        "/api/listings/",
        create_listing_payload(category=category.slug),
        format="json",
    )
    assert resp.status_code == 401


def test_create_listing_disallowed_without_can_list(renter_only_user):
    client = auth(renter_only_user)
    resp = client.post("/api/listings/", create_listing_payload(), format="json")
    assert resp.status_code == 403


def test_owner_can_update_listing(owner_user):
    client = auth(owner_user)
    create_resp = client.post("/api/listings/", create_listing_payload(), format="json")
    slug = create_resp.data["slug"]

    patch_resp = client.patch(
        f"/api/listings/{slug}/",
        {"daily_price_cad": "20.00", "is_available": False},
        format="json",
    )
    assert patch_resp.status_code == 200
    listing = Listing.objects.get(slug=slug)
    assert listing.daily_price_cad == Decimal("20.00")
    assert listing.is_available is False


def test_owner_cannot_change_owner_field(owner_user, renter_only_user):
    client = auth(owner_user)
    create_resp = client.post("/api/listings/", create_listing_payload(), format="json")
    slug = create_resp.data["slug"]

    patch_resp = client.patch(
        f"/api/listings/{slug}/",
        {"owner": renter_only_user.id, "daily_price_cad": "14.00"},
        format="json",
    )
    assert patch_resp.status_code == 200
    listing = Listing.objects.get(slug=slug)
    assert listing.owner_id == owner_user.id
    assert listing.daily_price_cad == Decimal("14.00")


def test_non_owner_cannot_modify_listing(owner_user, other_user):
    owner_client = auth(owner_user)
    create_resp = owner_client.post(
        "/api/listings/",
        create_listing_payload(),
        format="json",
    )
    slug = create_resp.data["slug"]

    other_client = auth(other_user)
    patch_resp = other_client.patch(
        f"/api/listings/{slug}/",
        {"title": "Unauthorized Update"},
        format="json",
    )
    assert patch_resp.status_code == 403
    listing = Listing.objects.get(slug=slug)
    assert listing.title == create_resp.data["title"]


def test_listing_list_and_filters(owner_user):
    tools = Category.objects.create(name="Power Tools")
    outdoors = Category.objects.create(name="Outdoors")
    visible_tools = make_listing(
        owner_user,
        title="Cordless Drill",
        description="Portable drill",
        daily_price_cad=Decimal("25.00"),
        city="Edmonton",
        category=tools,
    )
    visible_outdoors = make_listing(
        owner_user,
        title="Ski Roof Rack",
        description="Rack for winter trips",
        daily_price_cad=Decimal("65.00"),
        city="Calgary",
        category=outdoors,
    )
    make_listing(
        owner_user,
        title="Old Ladder",
        is_active=False,
    )
    make_listing(
        owner_user,
        title="Camping Stove",
        is_available=False,
    )

    client = APIClient()
    base_resp = client.get("/api/listings/")
    assert base_resp.status_code == 200
    slugs = {item["slug"] for item in base_resp.data}
    assert visible_tools.slug in slugs
    assert visible_outdoors.slug in slugs
    assert len(slugs) == 2

    price_min_resp = client.get("/api/listings/?price_min=60")
    assert {item["slug"] for item in price_min_resp.data} == {visible_outdoors.slug}

    price_max_resp = client.get("/api/listings/?price_max=30")
    assert {item["slug"] for item in price_max_resp.data} == {visible_tools.slug}

    search_resp = client.get("/api/listings/?q=drill")
    assert {item["slug"] for item in search_resp.data} == {visible_tools.slug}

    category_resp = client.get(f"/api/listings/?category={outdoors.slug}")
    assert {item["slug"] for item in category_resp.data} == {visible_outdoors.slug}

    city_resp = client.get("/api/listings/?city=calgary")
    assert {item["slug"] for item in city_resp.data} == {visible_outdoors.slug}
