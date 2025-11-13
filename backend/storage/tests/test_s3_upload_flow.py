from decimal import Decimal

import boto3
import pytest
from django.conf import settings
from moto import mock_aws

from listings.models import Listing, ListingPhoto


@pytest.fixture(autouse=True)
def _av_dummy_settings(settings):
    settings.AV_ENABLED = True
    settings.AV_ENGINE = "dummy"
    settings.AV_DUMMY_INFECT_MARKER = "EICAR"


@pytest.fixture
def s3_bucket(settings):
    with mock_aws():
        s3 = boto3.client(
            "s3",
            region_name=settings.AWS_S3_REGION_NAME,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
        )
        create_kwargs = {"Bucket": settings.AWS_STORAGE_BUCKET_NAME}
        region = settings.AWS_S3_REGION_NAME
        if region and region != "us-east-1":
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**create_kwargs)
        yield s3


@pytest.fixture
def owner(django_user_model):
    return django_user_model.objects.create_user(username="owner", password="x")


@pytest.fixture
def listing(owner, db):
    return Listing.objects.create(
        owner=owner,
        title="Photo Ready Listing",
        description="Listing for upload tests",
        daily_price_cad=Decimal("15.00"),
        replacement_value_cad=Decimal("100.00"),
        damage_deposit_cad=Decimal("25.00"),
        city="Edmonton",
    )


def auth_client(api_client, owner):
    api_client.force_authenticate(owner)
    return api_client


def _put_object_direct(s3, key, content, content_type="image/jpeg", tagging="av-status=pending"):
    s3.put_object(
        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=content_type,
        Tagging=tagging,
    )


@pytest.mark.django_db
def test_presign_owner_success(api_client, owner, listing, s3_bucket, settings):
    client = auth_client(api_client, owner)
    r = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "pic.jpg", "content_type": "image/jpeg", "size": 12345},
        format="json",
    )
    assert r.status_code == 200
    data = r.json()
    assert "upload_url" in data and "headers" in data
    assert data["key"].startswith(settings.S3_UPLOADS_PREFIX)


@pytest.mark.django_db
def test_complete_clean_creates_photo(api_client, owner, listing, s3_bucket):
    from storage.tasks import scan_and_finalize_photo

    client = auth_client(api_client, owner)
    presign = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "ok.jpg", "content_type": "image/jpeg", "size": 5000},
        format="json",
    ).json()
    key = presign["key"]
    _put_object_direct(s3_bucket, key, b"\xff\xd8\xff clean", "image/jpeg")
    r = client.post(
        f"/api/listings/{listing.id}/photos/complete",
        {
            "key": key,
            "etag": "test-etag",
            "filename": "ok.jpg",
            "content_type": "image/jpeg",
            "size": 5000,
        },
        format="json",
    )
    assert r.status_code == 202
    res = scan_and_finalize_photo(
        key=key,
        listing_id=listing.id,
        owner_id=owner.id,
        meta={
            "etag": "test-etag",
            "filename": "ok.jpg",
            "content_type": "image/jpeg",
            "size": 5000,
        },
    )
    assert res["status"] == "clean"
    photo = ListingPhoto.objects.get(listing=listing, key=key)
    assert photo.av_status == "clean" and photo.status == "active"


@pytest.mark.django_db
def test_complete_infected_blocks(api_client, owner, listing, s3_bucket):
    from storage.tasks import scan_and_finalize_photo

    client = auth_client(api_client, owner)
    presign = client.post(
        f"/api/listings/{listing.id}/photos/presign",
        {"filename": "bad.jpg", "content_type": "image/jpeg", "size": 5000},
        format="json",
    ).json()
    key = presign["key"]
    _put_object_direct(s3_bucket, key, b"xxx EICAR xxx", "image/jpeg")
    r = client.post(
        f"/api/listings/{listing.id}/photos/complete",
        {
            "key": key,
            "etag": "etag",
            "filename": "bad.jpg",
            "content_type": "image/jpeg",
            "size": 5000,
        },
        format="json",
    )
    assert r.status_code == 202
    res = scan_and_finalize_photo(
        key=key,
        listing_id=listing.id,
        owner_id=owner.id,
        meta={"etag": "etag"},
    )
    assert res["status"] == "infected"
    photo = ListingPhoto.objects.get(listing=listing, key=key)
    assert photo.status == ListingPhoto.Status.BLOCKED
    assert photo.av_status == ListingPhoto.AVStatus.INFECTED
