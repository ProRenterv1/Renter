from datetime import timedelta

import pytest
from django.utils import timezone

from bookings.models import Booking
from notifications import tasks
from notifications.models import NotificationLog
from operator_core.models import OperatorJobRun

pytestmark = pytest.mark.django_db


def test_detect_missing_notifications_job(booking_factory):
    now = timezone.now()
    b1 = booking_factory(
        start_date=now.date(),
        end_date=now.date() + timedelta(days=1),
        status=Booking.Status.REQUESTED,
    )
    b2 = booking_factory(
        start_date=now.date(),
        end_date=now.date() + timedelta(days=2),
        status=Booking.Status.PAID,
    )

    NotificationLog.objects.create(
        channel=NotificationLog.Channel.EMAIL,
        type="booking_request",
        status=NotificationLog.Status.SENT,
        booking_id=b1.id,
    )
    NotificationLog.objects.create(
        channel=NotificationLog.Channel.EMAIL,
        type="booking_request",
        status=NotificationLog.Status.SENT,
        booking_id=b2.id,
    )

    result = tasks.detect_missing_notifications.run(days=7)

    job = OperatorJobRun.objects.filter(job_name="detect_missing_notifications").latest(
        "created_at"
    )
    assert job.status == OperatorJobRun.Status.OK
    assert result["totals_scanned"] >= 2
    assert result["missing_by_type"]["status_update"] == 1
    assert result["missing_by_type"]["receipt"] == 1
    missing_ids = [item["booking_id"] for item in result["missing_bookings"]]
    assert b2.id in missing_ids
