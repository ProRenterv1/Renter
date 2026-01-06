"""Ensure dispute API responses include summary fields for UI cards."""

from __future__ import annotations

from datetime import date

import pytest

from bookings.models import Booking
from disputes.models import DisputeCase
from listings.models import ListingPhoto

pytestmark = pytest.mark.django_db


def test_dispute_summary_fields_present(api_client, booking_factory, owner_user, renter_user):
    start = date(2025, 1, 1)
    end = date(2025, 1, 5)
    booking = booking_factory(start_date=start, end_date=end, status=Booking.Status.PAID)

    ListingPhoto.objects.create(
        listing=booking.listing,
        owner=booking.owner,
        key="photo-key",
        url="https://example.com/photo.jpg",
        filename="photo.jpg",
        content_type="image/jpeg",
        size=123,
    )

    dispute = DisputeCase.objects.create(
        booking=booking,
        opened_by=owner_user,
        opened_by_role=DisputeCase.OpenedByRole.OWNER,
        category=DisputeCase.Category.DAMAGE,
        description="Broken tool",
        status=DisputeCase.Status.OPEN,
    )

    api_client.force_authenticate(owner_user)

    list_resp = api_client.get("/api/disputes/")
    assert list_resp.status_code == 200
    payload = list_resp.json()[0]

    assert payload["id"] == dispute.id
    assert payload["listing_title"] == booking.listing.title
    assert payload["listing_primary_photo_url"] == "https://example.com/photo.jpg"
    assert payload["booking_start_date"] == "2025-01-01"
    assert payload["booking_end_date"] == "2025-01-05"

    owner_summary = payload["owner_summary"]
    renter_summary = payload["renter_summary"]

    assert owner_summary["id"] == booking.owner_id
    assert owner_summary["name"]
    assert owner_summary["avatar_url"]

    assert renter_summary["id"] == booking.renter_id
    assert renter_summary["name"]
    assert renter_summary["avatar_url"]

    detail_resp = api_client.get(f"/api/disputes/{dispute.id}/")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["listing_title"] == booking.listing.title
    assert detail["listing_primary_photo_url"] == "https://example.com/photo.jpg"
    assert detail["booking_start_date"] == "2025-01-01"
    assert detail["booking_end_date"] == "2025-01-05"
