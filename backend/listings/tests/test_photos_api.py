from decimal import Decimal

import pytest
from django.utils.text import slugify
from rest_framework.test import APIClient

from listings.models import Listing, ListingPhoto

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _storage_defaults(settings):
    settings.AWS_STORAGE_BUCKET_NAME = settings.AWS_STORAGE_BUCKET_NAME or "test-bucket"
    settings.AWS_S3_REGION_NAME = settings.AWS_S3_REGION_NAME or "us-east-1"
    settings.AWS_S3_ENDPOINT_URL = settings.AWS_S3_ENDPOINT_URL or "https://example-s3.local"
    settings.S3_UPLOADS_PREFIX = "uploads/listings"
    settings.S3_MAX_UPLOAD_BYTES = 1024 * 1024


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(
        username="owner",
        password="x",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create_user(
        username="other",
        password="x",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def listing(owner):
    return Listing.objects.create(
        owner=owner,
        title="Cordless Saw",
        description="Handy job-site saw",
        daily_price_cad=Decimal("18.00"),
        replacement_value_cad=Decimal("150.00"),
        damage_deposit_cad=Decimal("50.00"),
        city="Edmonton",
    )


def _auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def test_photo_presign_requires_authentication(listing):
    client = APIClient()
    resp = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "tool.jpg", "content_type": "image/jpeg", "size": 100},
        format="json",
    )
    assert resp.status_code == 401


def test_photo_complete_requires_authentication(listing):
    client = APIClient()
    resp = client.post(
        f"/api/listings/{listing.id}/photos/complete",
        {
            "key": "uploads/listings/x.jpg",
            "etag": "etag",
            "filename": "photo.jpg",
            "content_type": "image/jpeg",
            "size": 50,
        },
        format="json",
    )
    assert resp.status_code == 401


def test_owner_can_presign_upload(monkeypatch, owner, listing):
    client = _auth_client(owner)

    stubbed = {
        "upload_url": "https://uploads.test/presigned",
        "headers": {"Content-Type": "image/jpeg", "x-amz-meta-test": "1"},
    }
    called = {}

    def fake_presign(key, **kwargs):
        called["key"] = key
        called["kwargs"] = kwargs
        return stubbed

    monkeypatch.setattr("listings.api.presign_put", fake_presign)

    payload = {
        "filename": "Drill Bit Set.JPG",
        "content_type": "image/jpeg",
        "size": 12345,
    }
    resp = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        payload,
        format="json",
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["upload_url"] == stubbed["upload_url"]
    assert data["headers"] == stubbed["headers"]
    assert data["max_bytes"] == 1024 * 1024
    assert data["tagging"] == "av-status=pending"

    key = data["key"]
    assert str(listing.id) in key
    assert str(listing.owner_id) in key
    assert slugify("Drill Bit Set") in key
    assert called["kwargs"]["content_type"] == "image/jpeg"
    assert called["kwargs"]["size_hint"] == payload["size"]


def test_non_owner_cannot_presign(monkeypatch, listing, other_user):
    client = _auth_client(other_user)

    def _should_not_run(*args, **kwargs):  # pragma: no cover - guard
        pytest.fail("presign_put should not be called for non-owners.")

    monkeypatch.setattr("listings.api.presign_put", _should_not_run)

    resp = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "bad.jpg", "content_type": "image/jpeg", "size": 100},
        format="json",
    )
    assert resp.status_code == 403


def test_presign_rejects_oversized_files(monkeypatch, owner, listing, settings):
    client = _auth_client(owner)

    def _should_not_run(*args, **kwargs):  # pragma: no cover - guard
        pytest.fail("presign_put should not be called when payload is invalid.")

    monkeypatch.setattr("listings.api.presign_put", _should_not_run)

    oversized = settings.S3_MAX_UPLOAD_BYTES + 1
    resp = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "tool.jpg", "content_type": "image/jpeg", "size": oversized},
        format="json",
    )
    assert resp.status_code == 400
    assert "File too large" in resp.json()["detail"]


def test_presign_rejects_when_photo_limit_reached(owner, listing, settings):
    client = _auth_client(owner)
    settings.LISTING_MAX_PHOTOS = 2
    ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key="uploads/listings/1/1/one.jpg",
        url="https://cdn.test/one.jpg",
        status=ListingPhoto.Status.ACTIVE,
    )
    ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key="uploads/listings/1/1/two.jpg",
        url="https://cdn.test/two.jpg",
        status=ListingPhoto.Status.PENDING,
    )

    resp = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "tool.jpg", "content_type": "image/jpeg", "size": 100},
        format="json",
    )

    assert resp.status_code == 400
    assert "Maximum of 2 photos" in resp.json()["detail"]


def test_presign_rejects_over_image_limit(owner, listing, settings):
    client = _auth_client(owner)
    settings.S3_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
    settings.IMAGE_MAX_UPLOAD_BYTES = 6 * 1024 * 1024
    too_large = settings.IMAGE_MAX_UPLOAD_BYTES + 1

    resp = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "tool.jpg", "content_type": "image/jpeg", "size": too_large},
        format="json",
    )

    assert resp.status_code == 400
    assert str(settings.IMAGE_MAX_UPLOAD_BYTES) in resp.json()["detail"]


def test_complete_rejects_large_dimensions(owner, listing, settings):
    client = _auth_client(owner)
    settings.IMAGE_MAX_DIMENSION = 100

    resp = client.post(
        f"/api/listings/{listing.id}/photos/complete",
        {
            "key": "uploads/listings/1/1/fake-key-wide.jpg",
            "etag": '"etag-1234"',
            "filename": "too-wide.jpg",
            "content_type": "image/jpeg",
            "size": 2048,
            "width": 200,
            "height": 50,
        },
        format="json",
    )
    assert resp.status_code == 400
    assert "dimension" in resp.json()["detail"]


def test_owner_can_complete_upload(monkeypatch, owner, listing):
    client = _auth_client(owner)

    delay_calls = {}

    def fake_delay(**kwargs):
        delay_calls["call"] = kwargs

    monkeypatch.setattr("listings.api.scan_and_finalize_photo.delay", fake_delay)

    payload = {
        "key": "uploads/listings/1/1/fake-key-drill.jpg",
        "etag": '"etag-1234"',
        "filename": "new-photo.jpg",
        "content_type": "image/jpeg",
        "size": 2048,
        "width": 800,
        "height": 600,
        "original_size": 3000000,
        "compressed_size": 2048,
    }
    resp = client.post(
        f"/api/listings/{listing.id}/photos/complete",
        payload,
        format="json",
    )
    assert resp.status_code == 202
    assert resp.json() == {"status": "queued", "key": payload["key"]}

    photo = ListingPhoto.objects.get(listing=listing, key=payload["key"])
    assert photo.status == ListingPhoto.Status.PENDING
    assert photo.av_status == ListingPhoto.AVStatus.PENDING
    assert photo.filename == payload["filename"]
    assert photo.content_type == payload["content_type"]
    assert photo.size == payload["size"]
    assert photo.width == payload["width"]
    assert photo.height == payload["height"]
    assert photo.etag == "etag-1234"

    queued = delay_calls["call"]
    assert queued["key"] == payload["key"]
    assert queued["listing_id"] == listing.id
    assert queued["owner_id"] == owner.id
    assert queued["meta"]["filename"] == payload["filename"]
    assert queued["meta"]["size"] == payload["size"]
    assert queued["meta"]["width"] == payload["width"]
    assert queued["meta"]["height"] == payload["height"]
    assert queued["meta"]["original_size"] == payload["original_size"]
    assert queued["meta"]["compressed_size"] == payload["compressed_size"]


def test_non_owner_cannot_complete(monkeypatch, listing, other_user):
    client = _auth_client(other_user)

    def _should_not_run(**kwargs):  # pragma: no cover - guard
        pytest.fail("scan task should not be queued for non-owners.")

    monkeypatch.setattr("listings.api.scan_and_finalize_photo.delay", _should_not_run)

    resp = client.post(
        f"/api/listings/{listing.id}/photos/complete",
        {
            "key": "uploads/x.jpg",
            "etag": "1",
            "filename": "x.jpg",
            "content_type": "image/jpeg",
            "size": 10,
        },
        format="json",
    )
    assert resp.status_code == 403
    assert ListingPhoto.objects.filter(listing=listing).count() == 0


def test_listing_detail_hides_non_visible_photos(owner, listing):
    clean_photo = ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key="uploads/listings/clean.jpg",
        url="https://cdn/clean.jpg",
        filename="clean.jpg",
        content_type="image/jpeg",
        size=512,
        etag="etag-clean",
        status=ListingPhoto.Status.ACTIVE,
        av_status=ListingPhoto.AVStatus.CLEAN,
    )
    ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key="uploads/listings/pending.jpg",
        url="https://cdn/pending.jpg",
        filename="pending.jpg",
        content_type="image/jpeg",
        size=256,
        etag="etag-pending",
        status=ListingPhoto.Status.PENDING,
        av_status=ListingPhoto.AVStatus.PENDING,
    )

    client = APIClient()
    resp = client.get(f"/api/listings/{listing.slug}/")
    assert resp.status_code == 200

    photos = resp.json()["photos"]
    keys = {photo["key"] for photo in photos}
    assert clean_photo.key in keys
    assert "uploads/listings/pending.jpg" not in keys
    for photo in photos:
        assert photo["status"] == ListingPhoto.Status.ACTIVE
        assert photo["av_status"] == ListingPhoto.AVStatus.CLEAN
