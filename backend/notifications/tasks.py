from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Sequence, Tuple

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone

from payments.receipts import upload_booking_receipt_pdf, upload_promotion_receipt_pdf

logger = logging.getLogger(__name__)
User = get_user_model()
CHECK_ID_MESSAGE = (
    "At pickup, please check the renter's government ID matches their profile name "
    "before handing over the tool."
)


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


def _build_email_context(extra: Optional[dict]) -> dict:
    frontend_origin = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    site_name = getattr(settings, "SITE_NAME", "Renter")
    site_tagline = getattr(
        settings,
        "SITE_TAGLINE",
        "Peer-to-peer rentals in Edmonton",
    )
    logo_url = getattr(settings, "SITE_LOGO_URL", "") or (
        f"{frontend_origin}/logo.png" if frontend_origin else ""
    )
    primary_color = getattr(settings, "SITE_PRIMARY_COLOR", "#5B8CA6")
    primary_text_color = getattr(settings, "SITE_PRIMARY_TEXT_COLOR", "#F4F9FC")
    heading_color = getattr(settings, "SITE_EMAIL_HEADING_COLOR", "#102030")
    text_color = getattr(settings, "SITE_EMAIL_TEXT_COLOR", "#1F2933")
    muted_text_color = getattr(settings, "SITE_EMAIL_MUTED_TEXT_COLOR", "#6B7280")
    background_color = getattr(settings, "SITE_EMAIL_BACKGROUND_COLOR", "#F2EFEE")
    card_color = getattr(settings, "SITE_EMAIL_CARD_COLOR", "#FFFFFF")
    surface_color = getattr(settings, "SITE_EMAIL_SURFACE_COLOR", "#F7F5F4")
    border_color = getattr(settings, "SITE_EMAIL_BORDER_COLOR", "#E5E7EB")
    site_initials = "".join(part[0].upper() for part in site_name.split()[:2]) or "R"

    context = {
        "logo_url": logo_url,
        "site_name": site_name,
        "site_tagline": site_tagline,
        "site_url": frontend_origin,
        "site_initials": site_initials,
        "brand_primary_color": primary_color,
        "brand_primary_text_color": primary_text_color,
        "brand_heading_color": heading_color,
        "brand_text_color": text_color,
        "brand_muted_text_color": muted_text_color,
        "brand_background_color": background_color,
        "brand_card_color": card_color,
        "brand_surface_color": surface_color,
        "brand_border_color": border_color,
    }
    if extra:
        context.update(extra)
    return context


Attachment = Tuple[str, bytes, str]


def _send_email(
    subject: str,
    template: str,
    context: dict,
    to_email: str | None,
    *,
    html_template: str | None = None,
    attachments: Optional[Sequence[Attachment]] = None,
) -> None:
    if not to_email:
        logger.warning("notifications: cannot send email without recipient")
        return
    context_with_brand = _build_email_context(context)
    context_with_brand["subject"] = subject
    text_template_path = f"email/{template}"
    body = _render(text_template_path, context_with_brand)

    derived_html_template = html_template
    if not derived_html_template:
        base_name = template.rsplit(".", 1)[0]
        derived_html_template = f"{base_name}.html"

    html_body = None
    if derived_html_template:
        html_template_path = (
            derived_html_template
            if derived_html_template.startswith("email/")
            else f"email/{derived_html_template}"
        )
        try:
            html_body = _render(html_template_path, context_with_brand)
        except TemplateDoesNotExist:
            html_body = None

    message = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )
    if html_body:
        message.attach_alternative(html_body, "text/html")
    for attachment in attachments or ():
        filename, content, mime_type = attachment
        message.attach(filename, content, mime_type)
    message.send(fail_silently=False)


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


def _display_name(user: Optional[User]) -> str:
    if not user:
        return "Unknown"
    full_name = ""
    if hasattr(user, "get_full_name"):
        full_name = (user.get_full_name() or "").strip()
    if not full_name:
        first = (getattr(user, "first_name", "") or "").strip()
        last = (getattr(user, "last_name", "") or "").strip()
        full_name = " ".join(part for part in (first, last) if part)
    if not full_name:
        username = getattr(user, "username", "") or ""
        if username:
            return username
        return str(user)
    return full_name


def _format_receipt_date(value: Optional[date]) -> str:
    if not value:
        return "N/A"
    # Use leading-zero-friendly format compatible with Windows/POSIX.
    return value.strftime("%b %d, %Y")


def _local_date(value):
    if not value:
        return None
    candidate = timezone.localtime(value) if timezone.is_aware(value) else value
    return candidate.date() if hasattr(candidate, "date") else None


def _format_booking_date_range(start: Optional[date], end_exclusive: Optional[date]):
    if start:
        start_display = _format_receipt_date(start)
    else:
        start_display = "N/A"
    if end_exclusive:
        inclusive_end = end_exclusive - timedelta(days=1)
    else:
        inclusive_end = start
    end_display = _format_receipt_date(inclusive_end) if inclusive_end else "N/A"
    return start_display, end_display, f"{start_display} - {end_display}"


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
    renter_first = (getattr(renter, "first_name", "") or "").strip()
    renter_last = (getattr(renter, "last_name", "") or "").strip()
    renter_full_name = " ".join(part for part in (renter_first, renter_last) if part).strip()
    if not renter_full_name:
        renter_full_name = _display_name(renter)
    context = {
        "owner": owner,
        "owner_full_name": _display_name(owner),
        "booking": booking,
        "listing_title": listing_title,
        "start_date": booking.start_date,
        "end_date": booking.end_date,
        "totals": booking.totals or {},
        "renter": renter,
        "renter_first_name": renter_first,
        "renter_last_name": renter_last,
        "renter_full_name": renter_full_name,
        "cta_url": f"{frontend_origin}/profile?tab=booking-requests" if frontend_origin else "",
        "check_id_message": CHECK_ID_MESSAGE,
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
        Booking.Status.PAID: "paid",
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


@shared_task(queue="emails")
def send_booking_completed_review_invite_email(booking_id: int):
    """
    Placeholder task for booking completion review invitations.
    """
    logger.info("notifications: review invite placeholder for booking %s", booking_id)


@shared_task(queue="emails")
def send_booking_expired_email(booking_id: int):
    """
    Notify both renter and owner that a booking expired before payment.
    """
    from bookings.models import Booking

    try:
        booking = Booking.objects.select_related("listing", "owner", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    listing_title = getattr(booking.listing, "title", "your listing")
    renter = booking.renter
    owner = booking.owner
    frontend_origin = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )
    base_context = {
        "booking": booking,
        "listing_title": listing_title,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
        "cta_url": f"{frontend_origin}/profile?tab=rentals" if frontend_origin else "",
    }

    renter_context = {
        **base_context,
        "recipient_role": "renter",
        "recipient_name": _display_name(renter),
    }
    _send_email(
        f"Your booking for {listing_title} expired",
        "booking_expired.txt",
        renter_context,
        getattr(renter, "email", None),
    )

    owner_context = {
        **base_context,
        "recipient_role": "owner",
        "recipient_name": _display_name(owner),
    }
    _send_email(
        f"A booking for {listing_title} expired",
        "booking_expired.txt",
        owner_context,
        getattr(owner, "email", None),
    )


@shared_task(queue="emails")
def send_booking_payment_receipt_email(user_id: int, booking_id: int):
    """Email the renter a receipt after payment succeeds."""
    user = _get_user(user_id)
    if not user or not getattr(user, "email", None):
        return

    try:
        from bookings.models import Booking

        booking = Booking.objects.select_related("listing", "owner", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    totals = booking.totals or {}
    attachments: list[Attachment] = []
    receipt_s3_key: str | None = None
    try:
        receipt_key, _, pdf_bytes = upload_booking_receipt_pdf(booking)
        receipt_s3_key = receipt_key
        attachments.append((f"{booking.id}_receipt.pdf", pdf_bytes, "application/pdf"))
    except Exception:
        logger.exception(
            "notifications: failed to generate/upload receipt PDF for booking %s",
            booking_id,
        )

    owner_full_name = _display_name(getattr(booking, "owner", None))
    tool_title = getattr(getattr(booking, "listing", None), "title", "your listing")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )
    context = {
        "user": user,
        "owner_full_name": owner_full_name,
        "tool_title": tool_title,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
        "total_paid": totals.get("total_charge") or "0.00",
        "receipt_s3_key": receipt_s3_key,
    }
    _send_email(
        "Your rental payment receipt",
        "booking_payment_receipt.txt",
        context,
        user.email,
        attachments=attachments or None,
    )


@shared_task(queue="emails")
def send_booking_completed_email(renter_id: int, booking_id: int) -> None:
    """Email the renter when their booking is marked completed."""
    from bookings.models import Booking

    renter = _get_user(renter_id)
    if not renter or not getattr(renter, "email", None):
        return

    try:
        booking = Booking.objects.select_related("listing", "owner", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    frontend_origin = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    totals = booking.totals or {}
    owner_full_name = _display_name(getattr(booking, "owner", None))
    tool_title = getattr(getattr(booking, "listing", None), "title", "your listing")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )

    subject = "Your rental is complete"
    if tool_title and tool_title != "your listing":
        subject = f"Your {tool_title} rental is complete"

    context = {
        "user": renter,
        "owner_full_name": owner_full_name,
        "tool_title": tool_title,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
        "totals": totals,
        "damage_deposit": totals.get("damage_deposit"),
        "cta_url": f"{frontend_origin}/profile?tab=rentals" if frontend_origin else "",
    }
    _send_email(
        subject,
        "booking_completed.txt",
        context,
        renter.email,
    )


@shared_task(queue="emails")
def send_promotion_payment_receipt_email(user_id: int, promotion_slot_id: int):
    """Email the listing owner a receipt after a promotion payment."""
    user = _get_user(user_id)
    if not user or not getattr(user, "email", None):
        return

    try:
        from promotions.models import PromotedSlot

        slot = PromotedSlot.objects.select_related("listing", "owner").get(pk=promotion_slot_id)
    except PromotedSlot.DoesNotExist:
        logger.warning("notifications: promotion slot %s no longer exists", promotion_slot_id)
        return

    def _format_cents(value: int | Decimal | None) -> str:
        return f"{(Decimal(value or 0) / Decimal('100')).quantize(Decimal('0.01'))}"

    attachments: list[Attachment] = []
    receipt_s3_key: str | None = None
    try:
        receipt_key, _, pdf_bytes = upload_promotion_receipt_pdf(slot)
        receipt_s3_key = receipt_key
        attachments.append((f"{slot.id}_promotion_receipt.pdf", pdf_bytes, "application/pdf"))
    except Exception:
        logger.exception(
            "notifications: failed to generate/upload promotion receipt PDF for slot %s",
            promotion_slot_id,
        )

    listing_title = getattr(slot.listing, "title", "your listing")
    start_display, end_display, date_range_display = _format_booking_date_range(
        _local_date(getattr(slot, "starts_at", None)),
        _local_date(getattr(slot, "ends_at", None)),
    )

    start_date = _local_date(getattr(slot, "starts_at", None))
    end_date_exclusive = _local_date(getattr(slot, "ends_at", None))
    duration_days = 0
    if start_date and end_date_exclusive:
        duration_days = max((end_date_exclusive - start_date).days, 1)

    context = {
        "user": user,
        "listing_title": listing_title,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
        "promotion_price": _format_cents(getattr(slot, "base_price_cents", 0)),
        "gst_amount": _format_cents(getattr(slot, "gst_cents", 0)),
        "price_per_day": _format_cents(getattr(slot, "price_per_day_cents", 0)),
        "duration_days": duration_days,
        "total_paid": _format_cents(getattr(slot, "total_price_cents", 0)),
        "receipt_s3_key": receipt_s3_key,
    }
    _send_email(
        "Your promotion payment receipt",
        "promotion_payment_receipt.txt",
        context,
        user.email,
        attachments=attachments or None,
    )


@shared_task(queue="emails")
def send_dispute_missing_evidence_email(dispute_id: int):
    """
    Placeholder for notifying filers to complete dispute evidence intake.
    """
    logger.info("notifications: dispute %s missing evidence email placeholder", dispute_id)


@shared_task(queue="emails")
def send_dispute_rebuttal_started_email(dispute_id: int, recipient_id: int):
    """Notify a participant that a dispute rebuttal window has started."""
    user = _get_user(recipient_id)
    if not user or not getattr(user, "email", None):
        return

    try:
        from disputes.models import DisputeCase

        dispute = (
            DisputeCase.objects.select_related("booking", "booking__listing", "opened_by")
            .filter(pk=dispute_id)
            .first()
        )
    except Exception:
        logger.exception(
            "notifications: failed loading dispute %s for rebuttal started email", dispute_id
        )
        return

    if not dispute or not dispute.booking:
        logger.warning("notifications: dispute %s missing booking for rebuttal started", dispute_id)
        return

    booking = dispute.booking
    listing_title = getattr(booking.listing, "title", "your rental")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )
    frontend_origin = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    if recipient_id == getattr(booking, "owner_id", None):
        cta_url = f"{frontend_origin}/profile?tab=booking-requests" if frontend_origin else ""
    elif recipient_id == getattr(booking, "renter_id", None):
        cta_url = f"{frontend_origin}/profile?tab=rentals" if frontend_origin else ""
    else:
        cta_url = frontend_origin or ""

    context = {
        "user": user,
        "recipient_name": _display_name(user),
        "booking": booking,
        "dispute": dispute,
        "listing_title": listing_title,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
        "cta_url": cta_url,
    }
    _send_email(
        f"Dispute opened on booking #{booking.id}",
        "dispute_rebuttal_started.txt",
        context,
        getattr(user, "email", None),
    )


@shared_task(queue="sms")
def send_dispute_rebuttal_started_sms(dispute_id: int, recipient_id: int):
    """SMS alert that a rebuttal window has started."""
    user = _get_user(recipient_id)
    to_number = getattr(user, "phone", None) if user else None
    if not user or not to_number:
        return

    try:
        from disputes.models import DisputeCase

        dispute = (
            DisputeCase.objects.select_related("booking", "booking__listing")
            .filter(pk=dispute_id)
            .first()
        )
    except Exception:
        logger.exception(
            "notifications: failed loading dispute %s for rebuttal started sms", dispute_id
        )
        return

    if not dispute or not dispute.booking:
        logger.warning(
            "notifications: dispute %s missing booking for rebuttal started sms", dispute_id
        )
        return

    booking = dispute.booking
    listing_title = getattr(booking.listing, "title", "your rental")
    context = {
        "user": user,
        "recipient_name": _display_name(user),
        "booking": booking,
        "listing_title": listing_title,
    }
    _send_sms("dispute_rebuttal_started.txt", context, to_number)


@shared_task(queue="emails")
def send_dispute_rebuttal_ended_email(dispute_id: int, recipient_id: int):
    """Notify a participant that the rebuttal window has ended."""
    user = _get_user(recipient_id)
    if not user or not getattr(user, "email", None):
        return

    try:
        from disputes.models import DisputeCase

        dispute = (
            DisputeCase.objects.select_related("booking", "booking__listing", "opened_by")
            .filter(pk=dispute_id)
            .first()
        )
    except Exception:
        logger.exception(
            "notifications: failed loading dispute %s for rebuttal ended email", dispute_id
        )
        return

    if not dispute or not dispute.booking:
        logger.warning("notifications: dispute %s missing booking for rebuttal ended", dispute_id)
        return

    booking = dispute.booking
    listing_title = getattr(booking.listing, "title", "your rental")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )
    frontend_origin = (getattr(settings, "FRONTEND_ORIGIN", "") or "").rstrip("/")
    if recipient_id == getattr(booking, "owner_id", None):
        cta_url = f"{frontend_origin}/profile?tab=booking-requests" if frontend_origin else ""
    elif recipient_id == getattr(booking, "renter_id", None):
        cta_url = f"{frontend_origin}/profile?tab=rentals" if frontend_origin else ""
    else:
        cta_url = frontend_origin or ""

    context = {
        "user": user,
        "recipient_name": _display_name(user),
        "booking": booking,
        "dispute": dispute,
        "listing_title": listing_title,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
        "cta_url": cta_url,
    }
    _send_email(
        f"Rebuttal window ended for booking #{booking.id}",
        "dispute_rebuttal_ended.txt",
        context,
        getattr(user, "email", None),
    )


@shared_task(queue="emails")
def send_deposit_failed_renter(booking_id: int, refund_amount: str):
    """Notify renter that booking was canceled due to failed deposit auth."""
    from bookings.models import Booking

    try:
        booking = Booking.objects.select_related("listing", "owner", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    renter = booking.renter
    listing_title = getattr(booking.listing, "title", "your booking")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )
    context = {
        "booking": booking,
        "listing_title": listing_title,
        "renter": renter,
        "refund_amount": refund_amount,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
    }
    _send_email(
        "Booking canceled: deposit could not be authorized",
        "deposit_failed_renter.txt",
        context,
        getattr(renter, "email", None),
    )
    _send_sms("deposit_failed_renter.txt", context, getattr(renter, "phone", None))


@shared_task(queue="emails")
def send_deposit_failed_owner(booking_id: int, owner_amount: str):
    """Notify owner that booking was canceled due to renter deposit failure."""
    from bookings.models import Booking

    try:
        booking = Booking.objects.select_related("listing", "owner", "renter").get(pk=booking_id)
    except Booking.DoesNotExist:
        logger.warning("notifications: booking %s no longer exists", booking_id)
        return

    owner = booking.owner
    listing_title = getattr(booking.listing, "title", "your listing")
    start_display, end_display, date_range_display = _format_booking_date_range(
        getattr(booking, "start_date", None),
        getattr(booking, "end_date", None),
    )
    context = {
        "booking": booking,
        "listing_title": listing_title,
        "owner": owner,
        "owner_amount": owner_amount,
        "start_date_display": start_display,
        "end_date_display": end_display,
        "date_range_display": date_range_display,
    }
    _send_email(
        "Booking canceled: renter deposit failed",
        "deposit_failed_owner.txt",
        context,
        getattr(owner, "email", None),
    )
    _send_sms("deposit_failed_owner.txt", context, getattr(owner, "phone", None))
