import logging
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.utils.formats import date_format

from bookings.models import Booking
from listings.models import Listing
from notifications import tasks

User = get_user_model()


@pytest.mark.django_db
def test_password_reset_email_contains_code(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"

    user = User.objects.create_user(
        username="email-user",
        email="email@example.com",
        password="secret123",
    )

    tasks.send_password_reset_code_email.run(user.id, user.email, "654321")

    assert len(mail.outbox) == 1
    assert "654321" in mail.outbox[0].body


@pytest.mark.django_db
def test_sms_task_noop_without_twilio(settings, caplog):
    settings.TWILIO_ACCOUNT_SID = None
    settings.TWILIO_AUTH_TOKEN = None
    settings.TWILIO_FROM_NUMBER = None

    user = User.objects.create_user(
        username="sms-user",
        email="sms@example.com",
        password="secret123",
        phone="+15551234567",
    )

    with caplog.at_level(logging.INFO):
        tasks.send_password_reset_code_sms.run(user.id, user.phone, "999999")

    assert "Twilio config incomplete" in caplog.text


@pytest.mark.django_db
def test_send_booking_request_email_includes_details(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    settings.FRONTEND_ORIGIN = "https://frontend.example"

    owner = User.objects.create_user(
        username="owner-email",
        email="owner@example.com",
        password="secret123",
        first_name="Olivia",
        last_name="Owner",
    )
    renter = User.objects.create_user(
        username="renter-user",
        email="renter@example.com",
        password="secret123",
        first_name="Rina",
        last_name="Renter",
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Adventure Tent",
        description="Sleeps 4 comfortably.",
        daily_price_cad=Decimal("50.00"),
        replacement_value_cad=Decimal("800.00"),
        damage_deposit_cad=Decimal("200.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )
    start = date.today() + timedelta(days=5)
    end = start + timedelta(days=3)
    booking = Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=start,
        end_date=end,
        status=Booking.Status.REQUESTED,
        totals={
            "days": "3",
            "rental_subtotal": "150.00",
            "service_fee": "15.00",
            "damage_deposit": "200.00",
            "total_charge": "365.00",
        },
    )

    tasks.send_booking_request_email.run(owner.id, booking.id)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "New booking request for Adventure Tent"
    body = message.body
    assert "Adventure Tent" in body
    assert renter.username in body
    assert settings.FRONTEND_ORIGIN in body
    assert date_format(start, use_l10n=True) in body
    assert date_format(end, use_l10n=True) in body


@pytest.mark.django_db
def test_send_booking_status_email_confirmed(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    settings.FRONTEND_ORIGIN = "https://frontend.example"

    owner = User.objects.create_user(
        username="owner",
        email="owner@example.com",
        password="secret123",
        first_name="Olivia",
        last_name="Owner",
    )
    renter = User.objects.create_user(
        username="renter",
        email="renter@example.com",
        password="secret123",
        first_name="Rina",
        last_name="Renter",
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Road Bike",
        description="Fast bike",
        daily_price_cad=Decimal("30.00"),
        replacement_value_cad=Decimal("900.00"),
        damage_deposit_cad=Decimal("150.00"),
        city="Calgary",
        is_active=True,
        is_available=True,
    )
    start = date.today() + timedelta(days=3)
    end = start + timedelta(days=2)
    booking = Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=start,
        end_date=end,
        status=Booking.Status.REQUESTED,
        totals={
            "rental_subtotal": "60.00",
            "service_fee": "6.00",
            "damage_deposit": "150.00",
            "total_charge": "216.00",
        },
    )

    tasks.send_booking_status_email.run(renter.id, booking.id, Booking.Status.CONFIRMED)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "Your booking for Road Bike was approved"
    body = message.body
    assert "Approved" in body
    assert listing.title in body
    assert settings.FRONTEND_ORIGIN in body
    assert renter.first_name in body
    assert date_format(start, use_l10n=True) in body
    assert date_format(end, use_l10n=True) in body
    assert "$216.00" in body


@pytest.mark.django_db
def test_send_booking_status_email_canceled(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    settings.FRONTEND_ORIGIN = "https://frontend.example"

    owner = User.objects.create_user(
        username="owner2",
        email="owner2@example.com",
        password="secret123",
        first_name="Owen",
        last_name="Owner",
    )
    renter = User.objects.create_user(
        username="renter2",
        email="renter2@example.com",
        password="secret123",
        first_name="Rhea",
        last_name="Renter",
    )
    listing = Listing.objects.create(
        owner=owner,
        title="Camera Kit",
        description="Pro camera",
        daily_price_cad=Decimal("40.00"),
        replacement_value_cad=Decimal("1200.00"),
        damage_deposit_cad=Decimal("300.00"),
        city="Edmonton",
        is_active=True,
        is_available=True,
    )
    start = date.today() + timedelta(days=4)
    end = start + timedelta(days=3)
    booking = Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=start,
        end_date=end,
        status=Booking.Status.REQUESTED,
        totals={
            "rental_subtotal": "120.00",
            "service_fee": "12.00",
            "damage_deposit": "300.00",
            "total_charge": "432.00",
        },
    )

    tasks.send_booking_status_email.run(renter.id, booking.id, Booking.Status.CANCELED)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "Your booking for Camera Kit was denied"
    body = message.body
    assert "Denied" in body
    assert listing.title in body
    assert settings.FRONTEND_ORIGIN in body
    assert "$432.00" in body
