from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking
from disputes.intake import update_dispute_intake_status
from disputes.models import DisputeCase

pytestmark = pytest.mark.django_db


def test_booking_return_sets_dispute_window_from_db_setting(
    api_client, owner_user, booking_factory, db_setting_factory
):
    db_setting_factory(key="DISPUTE_FILING_WINDOW_HOURS", value_json=1, value_type="int")
    booking = booking_factory(
        owner=owner_user,
        status=Booking.Status.PAID,
        returned_by_renter_at=timezone.now(),
    )

    api_client.force_authenticate(user=owner_user)
    resp = api_client.post(f"/api/bookings/{booking.id}/owner-mark-returned/")
    assert resp.status_code == 200, resp.json()

    booking.refresh_from_db()
    assert booking.return_confirmed_at is not None
    assert booking.dispute_window_expires_at is not None
    delta = booking.dispute_window_expires_at - booking.return_confirmed_at
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)


def test_dispute_intake_sets_rebuttal_due_from_db_setting(
    booking_factory, renter_user, dispute_factory, db_setting_factory
):
    db_setting_factory(key="DISPUTE_REBUTTAL_WINDOW_HOURS", value_json=2, value_type="int")
    booking = booking_factory(renter=renter_user, status=Booking.Status.PAID)
    filed_at = timezone.now()
    dispute = dispute_factory(
        booking=booking,
        opened_by=renter_user,
        category=DisputeCase.Category.DAMAGE,
        status=DisputeCase.Status.OPEN,
        filed_at=filed_at,
    )

    update_dispute_intake_status(dispute.id)
    dispute.refresh_from_db()
    assert dispute.rebuttal_due_at is not None
    delta = dispute.rebuttal_due_at - dispute.filed_at
    assert timedelta(hours=1, minutes=59) < delta < timedelta(hours=2, minutes=1)
