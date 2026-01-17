import io
import types
from datetime import timedelta
from decimal import Decimal

import pytest
from botocore.exceptions import ClientError
from celery.exceptions import Retry
from django.utils import timezone
from PIL import Image

from bookings.models import Booking, BookingPhoto
from disputes.models import DisputeCase, DisputeEvidence
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
def renter(django_user_model):
    return django_user_model.objects.create_user(
        username="renter-av",
        password="x",
        can_list=False,
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


@pytest.fixture
def booking(listing, owner, renter):
    today = timezone.localdate()
    return Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=today,
        end_date=today + timedelta(days=2),
        status=Booking.Status.PAID,
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


def test_extract_dimensions_skips_full_load(monkeypatch):
    img_bytes, dims = _image_bytes()

    def explode_on_load(self, *args, **kwargs):
        raise AssertionError("load should not be called when reading dimensions")

    monkeypatch.setattr(tasks.Image.Image, "load", explode_on_load)

    assert tasks._extract_dimensions(img_bytes) == dims


def test_extract_dimensions_falls_back_when_fast_kwarg_missing(monkeypatch):
    img_bytes, dims = _image_bytes()
    call_kwargs: list[dict] = []
    original_open = tasks.Image.open

    def fake_open(fp, *args, **kwargs):
        call_kwargs.append(kwargs)
        if kwargs.get("fast"):
            raise TypeError("fast not supported")
        return original_open(fp, *args, **kwargs)

    monkeypatch.setattr(tasks.Image, "open", fake_open)

    assert tasks._extract_dimensions(img_bytes) == dims
    assert call_kwargs and call_kwargs[0].get("fast") is True


def test_apply_av_metadata_tags_only(monkeypatch):
    tag_calls: list[tuple[str, dict[str, str]]] = []
    meta_calls: list[tuple] = []

    monkeypatch.setattr(
        "storage.tasks.s3util.tag_object", lambda key, tags: tag_calls.append((key, tags))
    )
    monkeypatch.setattr(
        "storage.tasks.s3util.set_metadata_copy",
        lambda *args, **kwargs: meta_calls.append((args, kwargs)),
    )

    tasks._apply_av_metadata("k", "clean")

    assert tag_calls == [("k", {"av-status": "clean"})]
    assert meta_calls == []


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


def test_scan_task_updates_booking_photo(monkeypatch, booking, renter):
    img_bytes, dims = _image_bytes()
    _stub_s3(monkeypatch, img_bytes)
    monkeypatch.setattr("storage.tasks._scan_bytes", lambda data: "clean")

    key = "uploads/bookings/clean/test.jpg"
    photo = BookingPhoto.objects.create(
        booking=booking,
        uploaded_by=renter,
        role=BookingPhoto.Role.BEFORE,
        s3_key=key,
        url="https://cdn.example/pending-booking.jpg",
        status=BookingPhoto.Status.PENDING,
        av_status=BookingPhoto.AVStatus.PENDING,
    )

    meta = {
        "etag": '"etag-booking"',
        "filename": "booking.jpg",
        "content_type": "image/jpeg",
        "size": 512,
        "role": BookingPhoto.Role.BEFORE,
    }
    result = tasks.scan_and_finalize_booking_photo.run(
        key=key,
        booking_id=booking.id,
        uploaded_by_id=renter.id,
        meta=meta,
    )
    photo.refresh_from_db()

    assert result["status"] == "clean"
    assert photo.status == BookingPhoto.Status.ACTIVE
    assert photo.av_status == BookingPhoto.AVStatus.CLEAN
    assert photo.filename == meta["filename"]
    assert photo.content_type == meta["content_type"]
    assert photo.size == meta["size"]
    assert photo.etag == "etag-booking"
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


def test_dispute_video_scan_uses_byte_limit(monkeypatch, booking, renter, settings):
    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=renter,
        opened_by_role=DisputeCase.OpenedByRole.RENTER,
        category=DisputeCase.Category.DAMAGE,
        description="Video evidence",
    )

    payload = b"x" * 5000
    download_calls: dict[str, object] = {}

    def _sliced_payload(extra_args):
        range_header = (extra_args or {}).get("Range")
        if not range_header:
            return payload
        try:
            start, end = range_header.replace("bytes=", "").split("-", 1)
            start_int = int(start)
            end_int = int(end)
            return payload[start_int : end_int + 1]
        except Exception:
            return payload

    class _StubClient:
        def download_fileobj(self, bucket, key, fileobj, ExtraArgs=None):
            download_calls["range"] = ExtraArgs
            fileobj.write(_sliced_payload(ExtraArgs))

    monkeypatch.setattr("storage.tasks._s3_client", lambda: _StubClient())
    monkeypatch.setattr("storage.tasks._apply_av_metadata", lambda *args, **kwargs: None)

    scanned: dict[str, int] = {}

    def fake_scan(data: bytes) -> str:
        scanned["len"] = len(data)
        return "clean"

    monkeypatch.setattr("storage.tasks._scan_bytes", fake_scan)
    settings.DISPUTE_VIDEO_SCAN_SAMPLE_BYTES = 1024

    result = tasks.scan_and_finalize_dispute_evidence(
        key="uploads/disputes/video.mp4",
        dispute_id=dispute.id,
        uploaded_by_id=renter.id,
        meta={
            "etag": '"etag-video"',
            "filename": "evidence.mp4",
            "content_type": "video/mp4",
            "size": len(payload),
            "kind": DisputeEvidence.Kind.VIDEO,
        },
    )

    evidence = DisputeEvidence.objects.get(dispute=dispute, uploaded_by=renter)
    assert result["status"] == "clean"
    assert evidence.av_status == DisputeEvidence.AVStatus.CLEAN
    assert scanned["len"] == settings.DISPUTE_VIDEO_SCAN_SAMPLE_BYTES
    assert download_calls["range"] is None
