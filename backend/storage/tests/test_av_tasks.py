import io
import types
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError
from celery.exceptions import Retry
from PIL import Image

from listings.models import Listing, ListingPhoto
from storage import tasks

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
        username="owner-av",
        password="x",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def listing(owner):
    return Listing.objects.create(
        owner=owner,
        title="Tripod",
        description="Camera tripod",
        daily_price_cad=Decimal("12.00"),
        replacement_value_cad=Decimal("60.00"),
        damage_deposit_cad=Decimal("20.00"),
        city="Calgary",
    )


def _image_bytes(size=(32, 24), color=(10, 120, 220)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue(), size


def _stub_s3(monkeypatch, payload: bytes):
    class _StubClient:
        def download_fileobj(self, bucket, key, fileobj):
            fileobj.write(payload)

    monkeypatch.setattr("storage.tasks._s3_client", lambda: _StubClient())


@pytest.fixture(autouse=True)
def _disable_metadata(monkeypatch):
    monkeypatch.setattr("storage.tasks._apply_av_metadata", lambda *args, **kwargs: None)


def test_scan_task_marks_photo_clean(monkeypatch, listing, owner):
    img_bytes, dims = _image_bytes()
    _stub_s3(monkeypatch, img_bytes)
    monkeypatch.setattr("storage.tasks._scan_bytes", lambda data: "clean")

    key = "uploads/listings/clean/test.jpg"
    photo = ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key=key,
        url="https://cdn.example/pending.jpg",
        status=ListingPhoto.Status.PENDING,
        av_status=ListingPhoto.AVStatus.PENDING,
    )

    meta = {
        "etag": '"etag-1"',
        "filename": "tripod.jpg",
        "content_type": "image/jpeg",
        "size": 4096,
    }
    result = tasks.scan_and_finalize_photo.run(
        key=key,
        listing_id=listing.id,
        owner_id=owner.id,
        meta=meta,
    )
    photo.refresh_from_db()

    assert result["status"] == "clean"
    assert photo.status == ListingPhoto.Status.ACTIVE
    assert photo.av_status == ListingPhoto.AVStatus.CLEAN
    assert photo.filename == meta["filename"]
    assert photo.content_type == meta["content_type"]
    assert photo.size == meta["size"]
    assert photo.etag == "etag-1"
    assert (photo.width, photo.height) == dims


def test_scan_task_blocks_infected_files(monkeypatch, listing, owner):
    img_bytes, dims = _image_bytes()
    _stub_s3(monkeypatch, img_bytes)
    monkeypatch.setattr("storage.tasks._scan_bytes", lambda data: "infected")

    key = "uploads/listings/infected/test.jpg"
    ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key=key,
        url="https://cdn.example/infected.jpg",
        status=ListingPhoto.Status.PENDING,
        av_status=ListingPhoto.AVStatus.PENDING,
    )

    meta = {
        "etag": '"etag-bad"',
        "filename": "infected.jpg",
        "content_type": "image/jpeg",
        "size": 1024,
    }
    result = tasks.scan_and_finalize_photo.run(
        key=key,
        listing_id=listing.id,
        owner_id=owner.id,
        meta=meta,
    )
    photo = ListingPhoto.objects.get(listing=listing, key=key)

    assert result["status"] == "infected"
    assert photo.status == ListingPhoto.Status.BLOCKED
    assert photo.av_status == ListingPhoto.AVStatus.INFECTED
    assert photo.filename == meta["filename"]
    assert photo.content_type == meta["content_type"]
    assert photo.size == meta["size"]
    assert photo.etag == "etag-bad"
    assert (photo.width, photo.height) == dims


def test_download_errors_trigger_task_retry(monkeypatch, listing, owner):
    class _ExplodingClient:
        def download_fileobj(self, bucket, key, fileobj):
            raise ClientError({"Error": {"Code": "404", "Message": "Missing"}}, "GetObject")

    monkeypatch.setattr("storage.tasks._s3_client", lambda: _ExplodingClient())

    retry_called = {}

    def fake_retry(self, exc=None, **kwargs):
        retry_called["exc"] = exc
        raise Retry()

    monkeypatch.setattr(
        tasks.scan_and_finalize_photo,
        "retry",
        types.MethodType(fake_retry, tasks.scan_and_finalize_photo),
    )

    with pytest.raises(Retry):
        tasks.scan_and_finalize_photo(
            key="uploads/listings/missing.jpg",
            listing_id=listing.id,
            owner_id=owner.id,
            meta={},
        )
    assert "Unable to download object" in str(retry_called["exc"])


def test_clamd_failure_falls_back_to_clamscan(monkeypatch, listing, owner, settings):
    settings.AV_ENGINE = "clamd"
    img_bytes, dims = _image_bytes(size=(16, 12))
    _stub_s3(monkeypatch, img_bytes)

    clamd_calls = {"count": 0}
    clamscan_calls = {"count": 0}

    def fake_clamd(data):
        clamd_calls["count"] += 1
        return None

    def fake_clamscan(data):
        clamscan_calls["count"] += 1
        return "clean"

    monkeypatch.setattr("storage.tasks._scan_with_clamd", fake_clamd)
    monkeypatch.setattr("storage.tasks._scan_with_clamscan", fake_clamscan)

    key = "uploads/listings/fallback/test.jpg"
    ListingPhoto.objects.create(
        listing=listing,
        owner=owner,
        key=key,
        url="https://cdn.example/fallback.jpg",
        status=ListingPhoto.Status.PENDING,
        av_status=ListingPhoto.AVStatus.PENDING,
    )

    result = tasks.scan_and_finalize_photo.run(
        key=key,
        listing_id=listing.id,
        owner_id=owner.id,
        meta={
            "etag": "etag-fallback",
            "filename": "fallback.jpg",
            "content_type": "image/jpeg",
            "size": 2048,
        },
    )
    photo = ListingPhoto.objects.get(listing=listing, key=key)

    assert clamd_calls["count"] == 1
    assert clamscan_calls["count"] == 1
    assert result["status"] == "clean"
    assert photo.status == ListingPhoto.Status.ACTIVE
    assert photo.av_status == ListingPhoto.AVStatus.CLEAN
    assert (photo.width, photo.height) == dims
