from datetime import timedelta

import pytest
from django.conf import settings
from django.core import mail
from django.utils import timezone

from bookings.models import Booking
from notifications import tasks
from notifications.models import NotificationLog
from operator_bookings.models import BookingEvent

pytestmark = pytest.mark.django_db


def test_email_logging_success(monkeypatch, booking_factory):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    start = timezone.localdate()
    end = start + timedelta(days=1)
    booking: Booking = booking_factory(
        start_date=start, end_date=end, status=Booking.Status.CONFIRMED
    )

    tasks._send_email_logged(
        "custom_type",
        to_email="user@example.com",
        subject="Test Subject",
        body="Hello",
        booking_id=booking.id,
    )

    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationLog.Status.SENT
    assert log.type == "custom_type"
    assert log.booking_id == booking.id
    assert len(mail.outbox) == 1
    assert BookingEvent.objects.filter(
        booking=booking, type=BookingEvent.Type.EMAIL_SENT, payload__notification_type="custom_type"
    ).exists()


def test_email_logging_failure(monkeypatch, booking_factory):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    booking: Booking = booking_factory(status=Booking.Status.CONFIRMED)

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tasks.EmailMultiAlternatives, "send", _raise)

    tasks._send_email_logged(
        "custom_fail",
        to_email="fail@example.com",
        subject="Test",
        body="Body",
        booking_id=booking.id,
    )

    log = NotificationLog.objects.latest("created_at")
    assert log.status == NotificationLog.Status.FAILED
    assert "boom" in log.error
    assert BookingEvent.objects.filter(
        booking=booking,
        type=BookingEvent.Type.EMAIL_FAILED,
        payload__notification_type="custom_fail",
    ).exists()
