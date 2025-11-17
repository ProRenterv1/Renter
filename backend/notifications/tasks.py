from __future__ import annotations

import logging
from typing import Optional

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)
User = get_user_model()


def _get_user(user_id: int) -> Optional[User]:
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("notifications: user %s no longer exists", user_id)
        return None


def _twilio_client():
    """Return a Twilio client and configured from number if available."""
    account_sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
    auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
    from_number = getattr(settings, "TWILIO_FROM_NUMBER", None)
    if not (account_sid and auth_token and from_number):
        logger.info("notifications: skipping SMS, Twilio config incomplete")
        return None, None
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        logger.warning("notifications: twilio SDK missing; SMS disabled")
        return None, None
    return Client(account_sid, auth_token), from_number


def _render(template: str, context: dict) -> str:
    """Render a template relative to the notifications app."""
    return render_to_string(template, context).strip()


def _send_email(subject: str, template: str, context: dict, to_email: str | None):
    if not to_email:
        logger.warning("notifications: cannot send email without recipient")
        return
    body = _render(f"email/{template}", context)
    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to_email], fail_silently=False)


def _send_sms(template: str, context: dict, to_number: str | None):
    if not to_number:
        logger.warning("notifications: cannot send SMS without destination")
        return
    client, from_number = _twilio_client()
    if not client or not from_number:
        # Already logged; act as a no-op for developer convenience
        return
    body = _render(f"sms/{template}", context)
    client.messages.create(body=body, from_=from_number, to=to_number)


@shared_task(queue="emails")
def send_password_reset_code_email(user_id: int, to_email: str, code: str):
    """Deliver the password reset challenge via email."""
    user = _get_user(user_id)
    context = {"user": user, "code": code}
    _send_email("Your password reset code", "password_reset_code.txt", context, to_email)


@shared_task(queue="sms")
def send_password_reset_code_sms(user_id: int, to_number: str, code: str):
    """Deliver the password reset challenge via SMS."""
    user = _get_user(user_id)
    context = {"user": user, "code": code}
    _send_sms("password_reset_code.txt", context, to_number)


@shared_task(queue="emails")
def send_two_factor_code_email(user_id: int, to_email: str, code: str):
    """Deliver the login two-factor code via email."""
    user = _get_user(user_id)
    context = {"user": user, "code": code}
    _send_email("Your login verification code", "two_factor_code.txt", context, to_email)


@shared_task(queue="sms")
def send_two_factor_code_sms(user_id: int, to_number: str, code: str):
    """Deliver the login two-factor code via SMS."""
    user = _get_user(user_id)
    context = {"user": user, "code": code}
    _send_sms("two_factor_code.txt", context, to_number)


@shared_task(queue="emails")
def send_contact_verification_email(user_id: int, to_email: str, code: str):
    """Deliver a verification code for confirming the user's email."""
    user = _get_user(user_id)
    context = {"user": user, "code": code}
    _send_email("Verify your email address", "contact_verification_code.txt", context, to_email)


@shared_task(queue="sms")
def send_contact_verification_sms(user_id: int, to_number: str, code: str):
    """Deliver a verification code for confirming the user's phone."""
    user = _get_user(user_id)
    context = {"user": user, "code": code}
    _send_sms("contact_verification_code.txt", context, to_number)


@shared_task(queue="emails")
def send_login_alert_email(user_id: int, ip: str, ua: str):
    """Alert the user that a new login occurred."""
    user = _get_user(user_id)
    if not user:
        return
    context = {"user": user, "ip": ip, "ua": ua}
    _send_email("New login detected", "login_alert.txt", context, user.email)


@shared_task(queue="sms")
def send_login_alert_sms(user_id: int, ip: str, ua: str):
    """SMS alert for login activity."""
    user = _get_user(user_id)
    if not user:
        return
    context = {"user": user, "ip": ip, "ua": ua}
    _send_sms("login_alert.txt", context, getattr(user, "phone", None))


@shared_task(queue="emails")
def send_password_changed_email(user_id: int):
    """Confirm that the user's password was updated."""
    user = _get_user(user_id)
    if not user:
        return
    context = {"user": user}
    _send_email("Your password was changed", "password_changed.txt", context, user.email)


@shared_task(queue="sms")
def send_password_changed_sms(user_id: int):
    """SMS confirmation for password change."""
    user = _get_user(user_id)
    if not user:
        return
    context = {"user": user}
    _send_sms("password_changed.txt", context, getattr(user, "phone", None))


@shared_task(queue="emails")
def send_booking_request_email(owner_id: int, booking_id: int):
    """Notify the listing owner that a renter submitted a new booking request."""
    from bookings.models import Booking

    owner = _get_user(owner_id)
    if not owner:
        return

    try:
        booking = Booking.objects.select_related("listing", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    listing_title = getattr(booking.listing, "title", "your listing")
    renter = booking.renter
    frontend_origin = getattr(settings, "FRONTEND_ORIGIN", "").rstrip("/") or ""
    context = {
        "owner": owner,
        "booking": booking,
        "listing_title": listing_title,
        "start_date": booking.start_date,
        "end_date": booking.end_date,
        "totals": booking.totals or {},
        "renter": renter,
        "cta_url": f"{frontend_origin}/profile?tab=booking-requests" if frontend_origin else "",
    }
    _send_email(
        f"New booking request for {listing_title}",
        "booking_request_new.txt",
        context,
        owner.email,
    )


@shared_task(queue="emails")
def send_booking_status_email(renter_id: int, booking_id: int, new_status: str):
    """Notify the renter that their booking status changed (e.g., approved or denied)."""
    from bookings.models import Booking

    renter = _get_user(renter_id)
    if not renter:
        return

    try:
        booking = Booking.objects.select_related("listing", "owner", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    listing_title = getattr(booking.listing, "title", "your listing")
    status_word_map = {
        Booking.Status.CONFIRMED: "approved",
        Booking.Status.CANCELED: "denied",
        Booking.Status.REQUESTED: "updated",
        Booking.Status.COMPLETED: "completed",
    }
    status_word = status_word_map.get(new_status, "updated")
    status_label = status_word.capitalize()
    frontend_origin = getattr(settings, "FRONTEND_ORIGIN", "").rstrip("/") or ""
    context = {
        "renter": renter,
        "booking": booking,
        "listing_title": listing_title,
        "status_label": status_label,
        "start_date": booking.start_date,
        "end_date": booking.end_date,
        "totals": booking.totals or {},
        "cta_url": f"{frontend_origin}/profile?tab=rentals" if frontend_origin else "",
        "owner": booking.owner,
    }
    _send_email(
        f"Your booking for {listing_title} was {status_word}",
        "booking_status_update.txt",
        context,
        getattr(renter, "email", None),
    )
