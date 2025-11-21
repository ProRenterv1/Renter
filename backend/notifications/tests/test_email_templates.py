from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from bookings.models import Booking
from listings.models import Listing
from notifications import tasks

User = get_user_model()


@pytest.fixture
def owner(settings):
    return User.objects.create_user(
        username="owner-html",
        email="owner@example.com",
        password="secret123",
        first_name="Olivia",
        last_name="Owner",
    )


@pytest.fixture
def renter(settings):
    return User.objects.create_user(
        username="renter-html",
        email="renter@example.com",
        password="secret123",
        first_name="Rina",
        last_name="Renter",
    )


@pytest.fixture
def listing(owner):
    return Listing.objects.create(
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


@pytest.fixture
def booking(listing, owner, renter):
    return Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=date.today() + timedelta(days=5),
        end_date=date.today() + timedelta(days=8),
        status=Booking.Status.REQUESTED,
        totals={
            "days": "3",
            "rental_subtotal": "150.00",
            "damage_deposit": "200.00",
            "service_fee": "15.00",
            "total_charge": "365.00",
        },
    )


@pytest.mark.django_db
def test_booking_request_email_has_html_and_button(settings, owner, renter, booking):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    settings.FRONTEND_ORIGIN = "https://renter.example"
    settings.SITE_LOGO_URL = "https://cdn.example/logo.png"
    settings.SITE_TAGLINE = "Peer-to-peer rentals in Edmonton"
    settings.SITE_PRIMARY_COLOR = "#5B8CA6"
    settings.SITE_PRIMARY_TEXT_COLOR = "#F4F9FC"
    if hasattr(mail, "outbox"):
        mail.outbox.clear()

    tasks.send_booking_request_email.run(owner.id, booking.id)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.alternatives, "HTML part missing"
    html_body, mime_type = message.alternatives[0]
    assert mime_type == "text/html"
    assert booking.listing.title in html_body
    full_name = f"{renter.first_name} {renter.last_name}".strip()
    assert full_name in html_body
    assert renter.username not in html_body
    cta_url = f"{settings.FRONTEND_ORIGIN}/profile?tab=booking-requests"
    assert f'href="{cta_url}"' in html_body
    assert "Review booking request" in html_body
    assert settings.SITE_PRIMARY_COLOR.lower() in html_body.lower()
    assert tasks.CHECK_ID_MESSAGE in html_body


@pytest.mark.django_db
def test_booking_emails_include_branding(settings, owner, renter, booking, monkeypatch):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    settings.FRONTEND_ORIGIN = "https://renter.example"
    settings.SITE_LOGO_URL = "https://cdn.example/logo.png"
    settings.SITE_TAGLINE = "Peer-to-peer rentals in Edmonton"
    settings.SITE_PRIMARY_COLOR = "#5B8CA6"
    if hasattr(mail, "outbox"):
        mail.outbox.clear()

    pdf_bytes = b"%PDF-test"

    def fake_upload(_booking):
        return (
            f"uploads/private/receipts/{_booking.id}_receipt.pdf",
            "https://example.test/receipt.pdf",
            pdf_bytes,
        )

    monkeypatch.setattr("notifications.tasks.upload_booking_receipt_pdf", fake_upload)

    tasks.send_booking_request_email.run(owner.id, booking.id)
    tasks.send_booking_status_email.run(renter.id, booking.id, Booking.Status.CONFIRMED)
    tasks.send_booking_payment_receipt_email.run(renter.id, booking.id)

    assert len(mail.outbox) == 3
    for message in mail.outbox:
        assert message.alternatives, "Expected HTML part"
        html_body, mime_type = message.alternatives[0]
        assert mime_type == "text/html"
        assert settings.SITE_LOGO_URL in html_body
        assert settings.SITE_TAGLINE in html_body
        assert settings.SITE_PRIMARY_COLOR.lower() in html_body.lower()


@pytest.mark.django_db
def test_contact_verification_email_has_html(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    settings.SITE_LOGO_URL = "https://cdn.example/logo.png"
    settings.SITE_TAGLINE = "Peer-to-peer rentals"
    settings.SITE_PRIMARY_COLOR = "#5B8CA6"
    user = User.objects.create_user(
        username="verify-user",
        email="verify@example.com",
        password="secret123",
        first_name="Vera",
        last_name="Verify",
    )
    if hasattr(mail, "outbox"):
        mail.outbox.clear()

    tasks.send_contact_verification_email.run(user.id, user.email, "654321")

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.alternatives
    html_body, mime_type = message.alternatives[0]
    assert mime_type == "text/html"
    assert "654321" in html_body
    assert settings.SITE_LOGO_URL in html_body
    assert settings.SITE_PRIMARY_COLOR.lower() in html_body.lower()
