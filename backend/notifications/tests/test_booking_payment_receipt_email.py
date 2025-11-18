from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core import mail

from bookings.models import Booking
from listings.models import Listing
from notifications import tasks

User = get_user_model()


@pytest.mark.django_db
def test_receipt_email_includes_pdf_attachment(settings, monkeypatch):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    if hasattr(mail, "outbox"):
        mail.outbox.clear()

    owner = User.objects.create_user(
        username="owner-receipt",
        email="owner@example.com",
        password="secret123",
        first_name="Olivia",
        last_name="Owner",
    )
    renter = User.objects.create_user(
        username="renter-receipt",
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
    booking = Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 4),
        status=Booking.Status.PAID,
        totals={
            "days": "3",
            "rental_subtotal": "150.00",
            "service_fee": "15.00",
            "damage_deposit": "200.00",
            "total_charge": "365.00",
        },
    )

    pdf_bytes = b"%PDF-1.4 test receipt"

    def fake_upload(booking_obj):
        return (
            f"uploads/private/receipts/{booking_obj.id}_receipt.pdf",
            "https://example.test/receipt.pdf",
            pdf_bytes,
        )

    monkeypatch.setattr("notifications.tasks.upload_booking_receipt_pdf", fake_upload)

    tasks.send_booking_payment_receipt_email.run(renter.id, booking.id)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "Your rental payment receipt"
    assert len(message.attachments) == 1
    attachment = message.attachments[0]
    assert attachment[0] == f"{booking.id}_receipt.pdf"
    assert attachment[1] == pdf_bytes
    assert attachment[2] == "application/pdf"

    body = message.body
    assert "Owner: Olivia Owner" in body
    assert "Tool: Adventure Tent" in body
    assert "Dates: Jul 01, 2025 - Jul 03, 2025" in body
    assert "Total paid: CAD $365.00" in body
    assert "Payment ID" not in body
    assert "Service fee" not in body


@pytest.mark.django_db
def test_receipt_email_still_sends_if_upload_fails(settings, monkeypatch):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@test.local"
    if hasattr(mail, "outbox"):
        mail.outbox.clear()

    owner = User.objects.create_user(
        username="owner-receipt-2",
        email="owner2@example.com",
        password="secret123",
        first_name="Owen",
        last_name="Owner",
    )
    renter = User.objects.create_user(
        username="renter-receipt-2",
        email="renter2@example.com",
        password="secret123",
        first_name="Rhea",
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
    booking = Booking.objects.create(
        listing=listing,
        owner=owner,
        renter=renter,
        start_date=date(2025, 8, 5),
        end_date=date(2025, 8, 7),
        status=Booking.Status.PAID,
        totals={
            "days": "2",
            "rental_subtotal": "60.00",
            "service_fee": "6.00",
            "damage_deposit": "150.00",
            "total_charge": "216.00",
        },
    )

    def blow_up(_booking):
        raise RuntimeError("upload failed")

    monkeypatch.setattr("notifications.tasks.upload_booking_receipt_pdf", blow_up)

    tasks.send_booking_payment_receipt_email.run(renter.id, booking.id)

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.subject == "Your rental payment receipt"
    assert message.attachments == []
    assert "Total paid: CAD $216.00" in message.body
