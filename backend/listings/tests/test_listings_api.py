from decimal import Decimal

import pytest
import responses
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from identity.models import IdentityVerification
from listings.api import GEOCODE_ENDPOINT
from listings.models import Category, Listing

pytestmark = pytest.mark.django_db

User = get_user_model()
CURRENCY_QUANTIZE = Decimal("0.01")


class DummyRedis:
    def __init__(self):
        self._data = {}

    def get(self, key):
        return self._data.get(key)

    def setex(self, key, ttl, value):
        if isinstance(value, str):
            self._data[key] = value.encode("utf-8")
        else:
            self._data[key] = value


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


def _format_currency(value: Decimal | str | float | int) -> str:
    return f"${Decimal(value).quantize(CURRENCY_QUANTIZE)}"


def listing_limit_error_message(settings) -> str:
    return (
        "To list tools with higher replacement value or damage deposit, please complete "
        "ID verification. Unverified owners are limited to "
        f"{_format_currency(settings.UNVERIFIED_MAX_REPLACEMENT_CAD)} replacement and "
        f"{_format_currency(settings.UNVERIFIED_MAX_DEPOSIT_CAD)} damage deposit per listing."
    )


def mark_user_identity_verified(user) -> None:
    IdentityVerification.objects.create(
        user=user,
        session_id=f"vs_listing_{user.id}",
        status=IdentityVerification.Status.VERIFIED,
        verified_at=timezone.now(),
    )


@pytest.fixture
def owner_user():
    return User.objects.create_user(
        username="owner",
        password="x",
        can_list=True,
        can_rent=True,
        email_verified=True,
        phone_verified=True,
    )


@pytest.fixture
def renter_only_user():
    return User.objects.create_user(
        username="renter",
        password="x",
        can_list=False,
        can_rent=True,
        email_verified=True,
        phone_verified=True,
    )


@pytest.fixture
def other_user():
    return User.objects.create_user(
        username="other",
        password="x",
        can_list=True,
        can_rent=True,
        email_verified=True,
        phone_verified=True,
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
        "postal_code": "T5K 2M5",
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
        "postal_code": "T5K 2M5",
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


def test_create_listing_blocked_for_unverified_high_values(owner_user, category, settings):
    client = auth(owner_user)
    payload = create_listing_payload(
        category=category.slug,
        replacement_value_cad="1500.00",
        damage_deposit_cad="900.00",
    )

    resp = client.post("/api/listings/", payload, format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == listing_limit_error_message(settings)


def test_update_listing_blocked_for_unverified_high_values(owner_user, category, settings):
    listing = make_listing(owner_user, category=category)
    client = auth(owner_user)
    payload = {"replacement_value_cad": "1500.00"}

    resp = client.patch(f"/api/listings/{listing.slug}/", payload, format="json")

    assert resp.status_code == 400
    assert resp.data["non_field_errors"][0] == listing_limit_error_message(settings)


def test_verified_owner_can_create_high_value_listing(owner_user, category, settings):
    mark_user_identity_verified(owner_user)
    client = auth(owner_user)
    payload = create_listing_payload(
        category=category.slug,
        replacement_value_cad="2000.00",
        damage_deposit_cad="900.00",
    )

    resp = client.post("/api/listings/", payload, format="json")

    assert resp.status_code == 201, resp.data
    assert resp.data["replacement_value_cad"] == payload["replacement_value_cad"]
    assert resp.data["damage_deposit_cad"] == payload["damage_deposit_cad"]


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("email_verified", "Please verify your email before creating listings."),
        ("phone_verified", "Please verify your phone before creating listings."),
    ],
)
def test_create_listing_requires_contact_verification(owner_user, field, message):
    setattr(owner_user, field, False)
    owner_user.save(update_fields=[field])
    client = auth(owner_user)

    resp = client.post("/api/listings/", create_listing_payload(), format="json")

    assert resp.status_code == 400
    assert resp.data["detail"] == message


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


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("email_verified", "Please verify your email before creating listings."),
        ("phone_verified", "Please verify your phone before creating listings."),
    ],
)
def test_owner_cannot_update_listing_without_verification(owner_user, field, message):
    client = auth(owner_user)
    create_resp = client.post("/api/listings/", create_listing_payload(), format="json")
    slug = create_resp.data["slug"]

    setattr(owner_user, field, False)
    owner_user.save(update_fields=[field])

    patch_resp = client.patch(
        f"/api/listings/{slug}/",
        {"daily_price_cad": "18.00"},
        format="json",
    )
    assert patch_resp.status_code == 400
    assert patch_resp.data["detail"] == message


def test_owner_cannot_update_listing_when_can_list_revoked(owner_user):
    client = auth(owner_user)
    create_resp = client.post("/api/listings/", create_listing_payload(), format="json")
    slug = create_resp.data["slug"]

    owner_user.can_list = False
    owner_user.save(update_fields=["can_list"])

    patch_resp = client.patch(
        f"/api/listings/{slug}/",
        {"daily_price_cad": "18.00"},
        format="json",
    )
    assert patch_resp.status_code == 400
    assert patch_resp.data["detail"] == "You are not allowed to create listings."


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
    assert {"count", "next", "previous", "results"} <= set(base_resp.data.keys())
    assert base_resp.data["count"] == 2
    slugs = {item["slug"] for item in base_resp.data["results"]}
    assert slugs == {visible_tools.slug, visible_outdoors.slug}

    price_min_resp = client.get("/api/listings/?price_min=60")
    assert {item["slug"] for item in price_min_resp.data["results"]} == {visible_outdoors.slug}

    price_max_resp = client.get("/api/listings/?price_max=30")
    assert {item["slug"] for item in price_max_resp.data["results"]} == {visible_tools.slug}

    search_resp = client.get("/api/listings/?q=drill")
    assert {item["slug"] for item in search_resp.data["results"]} == {visible_tools.slug}

    category_resp = client.get(f"/api/listings/?category={outdoors.slug}")
    assert {item["slug"] for item in category_resp.data["results"]} == {visible_outdoors.slug}

    city_resp = client.get("/api/listings/?city=calgary")
    assert {item["slug"] for item in city_resp.data["results"]} == {visible_outdoors.slug}


def test_listing_list_allows_invalid_bearer_token(owner_user):
    make_listing(owner_user, title="Public Listing")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
    resp = client.get("/api/listings/")
    assert resp.status_code == 200, resp.data
    assert resp.data["count"] == 1


def test_my_listings_requires_authentication():
    client = APIClient()
    resp = client.get("/api/listings/mine/")
    assert resp.status_code == 401


def test_my_listings_returns_only_owner_records(owner_user, other_user):
    oldest = make_listing(owner_user, title="Old Drill")
    make_listing(other_user, title="Other Listing")
    newest = make_listing(owner_user, title="New Drill")

    client = auth(owner_user)
    resp = client.get("/api/listings/mine/")
    assert resp.status_code == 200
    assert resp.data["count"] == 2
    slugs = [item["slug"] for item in resp.data["results"]]
    assert slugs == [newest.slug, oldest.slug]
    assert all(item["owner"] == owner_user.id for item in resp.data["results"])


def test_categories_endpoint_lists_all_categories():
    Category.objects.create(name="Camping Gear")
    Category.objects.create(name="Power Tools")

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
    resp = client.get("/api/listings/categories/")
    assert resp.status_code == 200
    names = [item["name"] for item in resp.data]
    assert names == ["Camping Gear", "Power Tools"]
    assert {"id", "name", "slug"} <= set(resp.data[0].keys())


def test_geocode_requires_postal_code(settings):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    client = APIClient()
    resp = client.get("/api/listings/geocode/")
    assert resp.status_code == 400


def test_geocode_requires_api_key(settings):
    settings.GOOGLE_MAPS_API_KEY = None
    client = APIClient()
    resp = client.get("/api/listings/geocode/?postal_code=T5K+2M5")
    assert resp.status_code == 503


def test_geocode_fetches_and_caches_coordinates(settings, monkeypatch):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    dummy_cache = DummyRedis()
    monkeypatch.setattr("listings.api.get_redis_client", lambda: dummy_cache)
    client = APIClient()

    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GEOCODE_ENDPOINT,
            json={
                "status": "OK",
                "results": [
                    {
                        "formatted_address": "T5K 2M5, Edmonton, AB",
                        "geometry": {"location": {"lat": 53.5, "lng": -113.5}},
                    }
                ],
            },
            status=200,
        )
        resp = client.get(
            "/api/listings/geocode/?postal_code=T5K+2M5&city=Edmonton&region=AB",
        )
        assert resp.status_code == 200
        assert resp.data["location"] == {"lat": 53.5, "lng": -113.5}
        assert resp.data["cache_hit"] is False
        assert len(rsps.calls) == 1

    with responses.RequestsMock() as rsps:
        resp_cached = client.get(
            "/api/listings/geocode/?postal_code=T5K+2M5&city=Edmonton&region=AB",
        )
        assert resp_cached.status_code == 200
        assert resp_cached.data["cache_hit"] is True
        assert resp_cached.data["location"] == {"lat": 53.5, "lng": -113.5}
        assert len(rsps.calls) == 0


def test_geocode_returns_404_for_unknown(settings, monkeypatch):
    settings.GOOGLE_MAPS_API_KEY = "test-key"
    dummy_cache = DummyRedis()
    monkeypatch.setattr("listings.api.get_redis_client", lambda: dummy_cache)
    client = APIClient()
    with responses.RequestsMock() as rsps:
        rsps.add(
            responses.GET,
            GEOCODE_ENDPOINT,
            json={"status": "ZERO_RESULTS", "results": []},
            status=200,
        )
        resp = client.get("/api/listings/geocode/?postal_code=00000")
    assert resp.status_code == 404
