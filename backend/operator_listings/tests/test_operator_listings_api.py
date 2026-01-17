import importlib
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework.test import APIClient

import renter.urls as renter_urls
from listings.models import Category, Listing, ListingPhoto
from operator_core.models import OperatorAuditEvent, OperatorNote, OperatorTag

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


@pytest.fixture
def operator_admin_user():
    group, _ = Group.objects.get_or_create(name="operator_admin")
    user = User.objects.create_user(
        username="operator_admin",
        email="operator_admin@example.com",
        password="pass123",
        is_staff=True,
    )
    user.groups.add(group)
    return user


def _ops_client(user=None):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    if user:
        client.force_authenticate(user=user)
    return client


def _results(resp):
    return (
        resp.data["results"]
        if isinstance(resp.data, dict) and "results" in resp.data
        else resp.data
    )


def test_operator_listings_requires_operator():
    listing_owner = User.objects.create_user(
        username="owner", email="o@example.com", password="pass123", is_staff=True
    )
    Listing.objects.create(
        owner=listing_owner,
        title="Saw",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
    )
    resp = _ops_client().get("/api/operator/listings/")
    assert resp.status_code in (401, 403)


def test_operator_listings_filters(operator_user, operator_admin_user):
    cat = Category.objects.create(name="Tools", slug="tools")
    owner_a = User.objects.create_user(
        username="a", email="a@example.com", password="pass", is_staff=True
    )
    owner_b = User.objects.create_user(
        username="b", email="b@example.com", password="pass", is_staff=True
    )
    now = timezone.now()
    older = now - timedelta(days=2)
    listing_in = Listing.objects.create(
        owner=owner_a,
        title="Camera",
        description="",
        category=cat,
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
    )
    Listing.objects.filter(pk=listing_in.id).update(created_at=now)
    listing_in.refresh_from_db()
    listing_out = Listing.objects.create(
        owner=owner_b,
        title="Drill",
        description="",
        category=None,
        daily_price_cad="5.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Calgary",
        is_active=False,
    )
    Listing.objects.filter(pk=listing_out.id).update(created_at=older)

    client = _ops_client(operator_admin_user)
    after = (now - timedelta(hours=1)).isoformat()
    before = (now + timedelta(hours=1)).isoformat()
    resp = client.get(
        "/api/operator/listings/",
        {
            "owner": owner_a.id,
            "city": "mont",
            "category": "tools",
            "is_active": True,
            "needs_review": False,
            "created_at_after": after,
            "created_at_before": before,
        },
    )

    assert resp.status_code == 200, resp.data
    payload = _results(resp)
    assert len(payload) == 1
    assert payload[0]["id"] == listing_in.id
    assert payload[0]["needs_review"] is False
    assert payload[0]["daily_price_cad"] == str(listing_in.daily_price_cad)


def test_operator_listing_detail_includes_photos_and_owner(operator_user, operator_admin_user):
    owner = User.objects.create_user(
        username="ownerx",
        email="ownerx@example.com",
        phone="+123",
        password="pass",
        is_staff=True,
        city="Vancouver",
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Tent",
        description="Nice tent",
        daily_price_cad="20.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Vancouver",
        is_active=True,
    )
    photo1 = ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key="a",
        url="http://example.com/a.jpg",
    )
    photo2 = ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key="b",
        url="http://example.com/b.jpg",
    )
    client = _ops_client(operator_admin_user)
    resp = client.get(f"/api/operator/listings/{listing.id}/")

    assert resp.status_code == 200, resp.data
    assert resp.data["owner"]["id"] == owner.id
    assert resp.data["owner"]["email"] == owner.email
    assert resp.data["owner"]["phone"] == owner.phone
    photos = resp.data["photos"]
    assert [p["id"] for p in photos] == [photo1.id, photo2.id]
    assert photos[0]["ordering"] == 0


def test_operator_listing_activate_deactivate_audits(operator_user, operator_admin_user):
    owner = User.objects.create_user(
        username="ownerz", email="ownerz@example.com", password="pass", is_staff=True
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Bike",
        description="",
        daily_price_cad="15.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Calgary",
        is_active=True,
    )
    client = _ops_client(operator_admin_user)

    resp = client.post(
        f"/api/operator/listings/{listing.id}/deactivate/", {"reason": "check"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    listing.refresh_from_db()
    assert listing.is_active is False
    audit = OperatorAuditEvent.objects.filter(
        entity_id=str(listing.id), action="operator.listing.deactivate"
    ).first()
    assert audit is not None
    assert audit.reason == "check"

    resp = client.post(
        f"/api/operator/listings/{listing.id}/activate/", {"reason": "ok"}, format="json"
    )
    assert resp.status_code == 200, resp.data
    listing.refresh_from_db()
    assert listing.is_active is True
    audit2 = OperatorAuditEvent.objects.filter(
        entity_id=str(listing.id), action="operator.listing.activate"
    ).first()
    assert audit2 is not None


def test_operator_listing_emergency_edit_audit(operator_user, operator_admin_user):
    owner = User.objects.create_user(
        username="ownerq", email="ownerq@example.com", password="pass", is_staff=True
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Old Title",
        description="Old Desc",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Toronto",
        is_active=True,
    )
    client = _ops_client(operator_admin_user)

    bad = client.patch(
        f"/api/operator/listings/{listing.id}/emergency-edit/",
        {"reason": "bad", "city": "Montreal"},
        format="json",
    )
    assert bad.status_code == 400

    resp = client.patch(
        f"/api/operator/listings/{listing.id}/emergency-edit/",
        {"reason": "fix", "title": "New Title", "description": "New Desc"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    listing.refresh_from_db()
    assert listing.title == "New Title"
    event = (
        OperatorAuditEvent.objects.filter(
            entity_id=str(listing.id), action="operator.listing.emergency_edit"
        )
        .order_by("-created_at")
        .first()
    )
    assert event is not None
    assert event.before_json == {"title": "Old Title", "description": "Old Desc"}
    assert event.after_json == {"title": "New Title", "description": "New Desc"}


def test_operator_listing_mark_needs_review_creates_note(operator_user):
    owner = User.objects.create_user(
        username="ownerr", email="ownerr@example.com", password="pass", is_staff=True
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Skis",
        description="",
        daily_price_cad="25.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Banff",
        is_active=True,
    )
    client = _ops_client(operator_user)

    resp = client.post(
        f"/api/operator/listings/{listing.id}/mark-needs-review/",
        {"reason": "flag", "text": "Check images"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    note = OperatorNote.objects.filter(object_id=str(listing.id)).first()
    assert note is not None
    tag = OperatorTag.objects.filter(name="needs_review", notes=note).first()
    assert tag is not None
    audit = OperatorAuditEvent.objects.filter(
        entity_id=str(listing.id), action="operator.listing.mark_needs_review"
    ).first()
    assert audit is not None
    list_resp = _ops_client(operator_user).get("/api/operator/listings/", {"needs_review": True})
    assert list_resp.status_code == 200
    ids = [row["id"] for row in _results(list_resp)]
    assert listing.id in ids


def test_operator_listings_include_recently_deleted(operator_admin_user, settings):
    settings.LISTING_SOFT_DELETE_RETENTION_DAYS = 3
    owner = User.objects.create_user(
        username="owner_deleted", email="owner_deleted@example.com", password="pass", is_staff=True
    )
    now = timezone.now()
    active_listing = Listing.objects.create(
        owner=owner,
        title="Active",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
    )
    recent_deleted = Listing.objects.create(
        owner=owner,
        title="Deleted Recent",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
        is_deleted=True,
        deleted_at=now - timedelta(days=1),
    )
    old_deleted = Listing.objects.create(
        owner=owner,
        title="Deleted Old",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
        is_deleted=True,
        deleted_at=now - timedelta(days=5),
    )

    client = _ops_client(operator_admin_user)
    resp = client.get("/api/operator/listings/", {"include_deleted": "true"})
    assert resp.status_code == 200, resp.data
    ids = [row["id"] for row in _results(resp)]
    assert active_listing.id in ids
    assert recent_deleted.id in ids
    assert old_deleted.id not in ids


def test_operator_listing_detail_allows_recently_deleted(operator_admin_user, settings):
    settings.LISTING_SOFT_DELETE_RETENTION_DAYS = 3
    owner = User.objects.create_user(
        username="owner_deleted_detail",
        email="owner_deleted_detail@example.com",
        password="pass",
        is_staff=True,
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Deleted Detail",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
        is_deleted=True,
        deleted_at=timezone.now() - timedelta(days=1),
    )
    client = _ops_client(operator_admin_user)
    resp = client.get(f"/api/operator/listings/{listing.id}/")
    assert resp.status_code == 200, resp.data
    assert resp.data["is_deleted"] is True
    assert resp.data["deleted_at"] is not None


def test_operator_listings_hide_recently_deleted_for_non_admin(operator_user, settings):
    settings.LISTING_SOFT_DELETE_RETENTION_DAYS = 3
    owner = User.objects.create_user(
        username="owner_deleted_support",
        email="owner_deleted_support@example.com",
        password="pass",
        is_staff=True,
    )
    now = timezone.now()
    active_listing = Listing.objects.create(
        owner=owner,
        title="Active",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
    )
    recent_deleted = Listing.objects.create(
        owner=owner,
        title="Deleted Recent",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
        is_deleted=True,
        deleted_at=now - timedelta(days=1),
    )
    client = _ops_client(operator_user)
    resp = client.get("/api/operator/listings/", {"include_deleted": "true"})
    assert resp.status_code == 200, resp.data
    ids = [row["id"] for row in _results(resp)]
    assert active_listing.id in ids
    assert recent_deleted.id not in ids


def test_operator_listing_detail_denies_recently_deleted_for_non_admin(operator_user, settings):
    settings.LISTING_SOFT_DELETE_RETENTION_DAYS = 3
    owner = User.objects.create_user(
        username="owner_deleted_support_detail",
        email="owner_deleted_support_detail@example.com",
        password="pass",
        is_staff=True,
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Deleted Detail",
        description="",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        is_active=True,
        is_deleted=True,
        deleted_at=timezone.now() - timedelta(days=1),
    )
    client = _ops_client(operator_user)
    resp = client.get(f"/api/operator/listings/{listing.id}/")
    assert resp.status_code == 404
