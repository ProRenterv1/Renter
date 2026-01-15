from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from bookings.models import Booking
from listings.models import Listing
from payments.receipts import (
    _extract_owner_earnings_breakdown,
    _extract_payment_breakdown,
    render_booking_receipt_pdf,
    render_owner_earnings_statement_pdf,
    render_promotion_receipt_pdf,
    upload_booking_receipt_pdf,
    upload_owner_earnings_statement_pdf,
    upload_promotion_receipt_pdf,
)
from promotions.models import PromotedSlot
from storage import s3 as storage_s3

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def owner_user():
    return User.objects.create_user(username="owner_receipt", password="test-pass")


@pytest.fixture
def renter_user():
    return User.objects.create_user(username="renter_receipt", password="test-pass")


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Circular Saw",
        description="Power saw for rent",
        daily_price_cad=Decimal("45.00"),
        replacement_value_cad=Decimal("400.00"),
        damage_deposit_cad=Decimal("120.00"),
        city="Edmonton",
        postal_code="T5K 2M5",
        is_active=True,
        is_available=True,
    )


@pytest.fixture
def promotion_slot(listing, owner_user):
    start = timezone.now()
    return PromotedSlot.objects.create(
        listing=listing,
        owner=owner_user,
        price_per_day_cents=1500,
        base_price_cents=10500,
        gst_cents=525,
        total_price_cents=11025,
        starts_at=start,
        ends_at=start + timedelta(days=7),
        stripe_session_id="pi_promo_123",
    )


def test_render_booking_receipt_pdf_returns_pdf_bytes(listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 4),
        charge_payment_intent_id="pi_charge_12345",
        deposit_hold_id="pi_deposit_987",
        totals={
            "days": "3",
            "rental_subtotal": "135.00",
            "renter_fee": "20.25",
            "service_fee": "20.25",
            "damage_deposit": "120.00",
            "total_charge": "275.25",
        },
    )

    pdf_bytes = render_booking_receipt_pdf(booking)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes
    assert pdf_bytes.startswith(b"%PDF")


def test_render_owner_earnings_statement_pdf_returns_pdf_bytes(listing, owner_user, renter_user):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 4),
        charge_payment_intent_id="pi_charge_owner",
        totals={
            "days": "3",
            "rental_subtotal": "135.00",
            "owner_fee_base": "6.75",
            "owner_fee_gst": "0.34",
            "owner_fee_total": "7.09",
            "owner_payout": "127.91",
            "total_charge": "155.25",
        },
    )

    pdf_bytes = render_owner_earnings_statement_pdf(booking)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes
    assert pdf_bytes.startswith(b"%PDF")


def test_extract_payment_breakdown_includes_gst_fields():
    totals = {
        "rental_subtotal": "100.00",
        "renter_fee_base": "10.00",
        "renter_fee_gst": "0.50",
        "renter_fee_total": "10.50",
        "damage_deposit": "0.00",
        "total_charge": "110.50",
        "gst_enabled": True,
        "gst_rate": "0.05",
    }
    breakdown = _extract_payment_breakdown(totals)

    assert breakdown.rent == Decimal("100.00")
    assert breakdown.service_fee == Decimal("10.00")
    assert breakdown.service_fee_gst == Decimal("0.50")
    assert breakdown.service_fee_total == Decimal("10.50")
    assert breakdown.total_charge == Decimal("110.50")


def test_extract_owner_earnings_breakdown_includes_gst_fields():
    totals = {
        "rental_subtotal": "100.00",
        "owner_fee_base": "5.00",
        "owner_fee_gst": "0.25",
        "owner_payout": "94.75",
    }
    breakdown = _extract_owner_earnings_breakdown(totals)

    assert breakdown.rental_subtotal == Decimal("100.00")
    assert breakdown.owner_fee_base == Decimal("5.00")
    assert breakdown.owner_fee_gst == Decimal("0.25")
    assert breakdown.owner_payout == Decimal("94.75")


def test_render_promotion_receipt_pdf_returns_pdf_bytes(promotion_slot):
    pdf_bytes = render_promotion_receipt_pdf(promotion_slot)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes
    assert pdf_bytes.startswith(b"%PDF")


def test_upload_booking_receipt_pdf_uploads_and_returns_key(
    listing, owner_user, renter_user, settings, monkeypatch
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=date(2025, 8, 10),
        end_date=date(2025, 8, 13),
        charge_payment_intent_id="pi_charge_upload",
        totals={
            "days": "3",
            "rental_subtotal": "135.00",
            "renter_fee": "20.25",
            "service_fee": "20.25",
            "damage_deposit": "120.00",
            "total_charge": "275.25",
        },
    )

    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_REGION_NAME = "ca-central-1"
    settings.AWS_S3_ENDPOINT_URL = ""

    class _StubS3Client:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    stub_client = _StubS3Client()
    monkeypatch.setattr("payments.receipts.storage_s3._client", lambda: stub_client)

    key, url, pdf_bytes = upload_booking_receipt_pdf(booking)

    expected_key = f"uploads/private/receipts/{booking.id}_receipt.pdf"
    assert key == expected_key
    expected_url = storage_s3.public_url(expected_key)
    assert url == expected_url
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")

    assert len(stub_client.calls) == 1
    call = stub_client.calls[0]
    assert call["Bucket"] == settings.AWS_STORAGE_BUCKET_NAME
    assert call["Key"] == expected_key
    assert call["ContentType"] == "application/pdf"
    assert call["Body"] == pdf_bytes


def test_upload_promotion_receipt_pdf_uploads_and_returns_key(
    promotion_slot, settings, monkeypatch
):
    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_REGION_NAME = "ca-central-1"
    settings.AWS_S3_ENDPOINT_URL = ""

    class _StubS3Client:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    stub_client = _StubS3Client()
    monkeypatch.setattr("payments.receipts.storage_s3._client", lambda: stub_client)

    key, url, pdf_bytes = upload_promotion_receipt_pdf(promotion_slot)

    expected_key = f"uploads/private/receipts/promotions/{promotion_slot.id}_promotion_receipt.pdf"
    assert key == expected_key
    expected_url = storage_s3.public_url(expected_key)
    assert url == expected_url
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")

    assert len(stub_client.calls) == 1
    call = stub_client.calls[0]
    assert call["Bucket"] == settings.AWS_STORAGE_BUCKET_NAME
    assert call["Key"] == expected_key
    assert call["ContentType"] == "application/pdf"
    assert call["Body"] == pdf_bytes


def test_upload_owner_earnings_statement_pdf_uploads_and_returns_key(
    listing, owner_user, renter_user, settings, monkeypatch
):
    booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=date(2025, 8, 10),
        end_date=date(2025, 8, 13),
        charge_payment_intent_id="pi_charge_owner_upload",
        totals={
            "days": "3",
            "rental_subtotal": "135.00",
            "owner_fee_base": "6.75",
            "owner_fee_gst": "0.34",
            "owner_fee_total": "7.09",
            "owner_payout": "127.91",
            "total_charge": "155.25",
        },
    )

    settings.AWS_STORAGE_BUCKET_NAME = "test-bucket"
    settings.AWS_S3_REGION_NAME = "ca-central-1"
    settings.AWS_S3_ENDPOINT_URL = ""

    class _StubS3Client:
        def __init__(self):
            self.calls = []

        def put_object(self, **kwargs):
            self.calls.append(kwargs)
            return {"ResponseMetadata": {"HTTPStatusCode": 200}}

    stub_client = _StubS3Client()
    monkeypatch.setattr("payments.receipts.storage_s3._client", lambda: stub_client)

    key, url, pdf_bytes = upload_owner_earnings_statement_pdf(booking)

    expected_key = f"uploads/private/owner-statements/{booking.id}_owner_statement.pdf"
    assert key == expected_key
    expected_url = storage_s3.public_url(expected_key)
    assert url == expected_url
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")

    assert len(stub_client.calls) == 1
    call = stub_client.calls[0]
    assert call["Bucket"] == settings.AWS_STORAGE_BUCKET_NAME
    assert call["Key"] == expected_key
    assert call["ContentType"] == "application/pdf"
    assert call["Body"] == pdf_bytes
