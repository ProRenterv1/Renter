import importlib
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import clear_url_caches
from django.utils import timezone
from rest_framework.test import APIClient

import renter.urls as renter_urls
from listings.models import Listing
from operator_core.models import OperatorAuditEvent
from promotions.models import PromotedSlot

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
def owner_user():
    return User.objects.create_user(
        username="owner",
        email="owner@example.com",
        password="pass123",
    )


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Drill",
        description="desc",
        daily_price_cad="10.00",
        replacement_value_cad="0",
        damage_deposit_cad="0",
        city="Edmonton",
        postal_code="T0T0T0",
    )


def _authed_client(user):
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    client.force_authenticate(user=user)
    return client


def test_permissions(listing, owner_user):
    PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=100,
        base_price_cents=100,
        gst_cents=5,
        total_price_cents=105,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=1),
        active=True,
    )
    client = APIClient()
    client.defaults["HTTP_HOST"] = "ops.example.com"
    resp = client.get("/api/operator/promotions/")
    assert resp.status_code in (401, 403)


def test_reason_required(operator_user):
    client = _authed_client(operator_user)
    resp = client.post(
        "/api/operator/promotions/grant-comped/",
        {
            "listing_id": 1,
            "starts_at": timezone.now().isoformat(),
            "ends_at": timezone.now().isoformat(),
        },
        format="json",
    )
    assert resp.status_code == 400


def test_list_filters(operator_user, listing, owner_user):
    active_slot = PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=100,
        base_price_cents=100,
        gst_cents=5,
        total_price_cents=105,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=1),
        active=True,
    )
    inactive_slot = PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=100,
        base_price_cents=100,
        gst_cents=5,
        total_price_cents=105,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=1),
        active=False,
    )

    client = _authed_client(operator_user)
    resp = client.get(f"/api/operator/promotions/?active=true&owner_id={owner_user.id}")
    assert resp.status_code == 200
    ids = (
        [row["id"] for row in resp.data["results"]]
        if "results" in resp.data
        else [row["id"] for row in resp.data]
    )
    assert active_slot.id in ids
    assert inactive_slot.id not in ids


def test_grant_comped_creates_slot_and_audit(operator_user, listing):
    client = _authed_client(operator_user)
    start = timezone.now()
    end = start + timedelta(days=2)
    resp = client.post(
        "/api/operator/promotions/grant-comped/",
        {
            "reason": "comped",
            "listing_id": listing.id,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
        },
        format="json",
    )
    assert resp.status_code == 201
    slot_id = resp.data["id"]
    assert PromotedSlot.objects.filter(pk=slot_id, active=True).exists()
    assert OperatorAuditEvent.objects.filter(action="operator.promo.grant_comped").exists()


def test_cancel_early_updates_slot_and_audit(operator_user, listing, owner_user):
    slot = PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=100,
        base_price_cents=100,
        gst_cents=5,
        total_price_cents=105,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=3),
        active=True,
    )
    client = _authed_client(operator_user)
    resp = client.post(
        f"/api/operator/promotions/{slot.id}/cancel-early/",
        {"reason": "stop"},
        format="json",
    )
    assert resp.status_code == 200
    slot.refresh_from_db()
    assert slot.active is False
    assert slot.ends_at <= timezone.now()
    assert OperatorAuditEvent.objects.filter(action="operator.promo.cancel_early").exists()
