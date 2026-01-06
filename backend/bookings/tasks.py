"""Celery tasks for bookings."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from celery import shared_task
from django.db import models
from django.utils import timezone

from notifications import tasks as notification_tasks
from payments.stripe_api import (
    DepositAuthorizationInsufficientFunds,
    StripeConfigurationError,
    StripePaymentError,
    StripeTransientError,
    create_booking_deposit_hold_intent,
    create_owner_transfer_for_booking,
    release_deposit_hold,
)

from .domain import is_pre_payment, mark_canceled, settle_and_cancel_for_deposit_failure
from .models import Booking

logger = logging.getLogger(__name__)

EXPIRED_REASON = "Booking expired before payment."


@shared_task(name="bookings.auto_expire_stale_bookings")
def auto_expire_stale_bookings() -> int:
    """
    Cancel stale, pre-payment bookings that never moved forward.

    Returns the number of bookings automatically expired.
    """
    today: date = timezone.localdate()
    expired_count = 0
    update_fields = [
        "status",
        "canceled_by",
        "canceled_reason",
        "auto_canceled",
        "updated_at",
    ]

    requested_qs = Booking.objects.filter(
        status=Booking.Status.REQUESTED,
        start_date__lte=today,
    ).select_related("listing", "owner", "renter")

    confirmed_qs = Booking.objects.filter(
        status=Booking.Status.CONFIRMED,
        start_date__lte=today,
    ).select_related("listing", "owner", "renter")

    def _expire_booking(booking: Booking) -> None:
        nonlocal expired_count
        if booking.is_terminal():
            return
        mark_canceled(booking, actor="system", auto=True, reason=EXPIRED_REASON)
        booking.save(update_fields=update_fields)
        expired_count += 1
        try:
            notification_tasks.send_booking_expired_email.delay(booking.id)
        except Exception:
            logger.info(
                "notifications: failed to queue booking_expired_email",
                extra={"booking_id": booking.id},
                exc_info=True,
            )

    for booking in requested_qs:
        _expire_booking(booking)

    for booking in confirmed_qs:
        if not is_pre_payment(booking):
            continue
        _expire_booking(booking)

    return expired_count


@shared_task(name="bookings.auto_release_deposits")
def auto_release_deposits() -> int:
    """
    Automatically release damage deposit holds after their scheduled time,
    once the booking is completed and no dispute window is open.

    Returns the number of bookings where a deposit was released.
    """
    now = timezone.now()
    released_count = 0

    qs = (
        Booking.objects.filter(
            status=Booking.Status.COMPLETED,
            deposit_hold_id__isnull=False,
            deposit_hold_id__gt="",
            deposit_released_at__isnull=True,
            deposit_release_scheduled_at__lte=now,
            deposit_locked=False,
        )
        .filter(
            models.Q(dispute_window_expires_at__isnull=True)
            | models.Q(dispute_window_expires_at__lte=now)
        )
        .select_related("renter")
    )

    for booking in qs:
        try:
            release_deposit_hold(booking)
        except Exception:
            logger.exception("auto_release_deposits: failed for booking %s", booking.id)
            continue

        booking.deposit_released_at = timezone.now()
        booking.save(update_fields=["deposit_released_at", "updated_at"])
        released_count += 1

    return released_count


def _deposit_amount(booking: Booking) -> Decimal:
    totals = booking.totals or {}
    try:
        return Decimal(str(totals.get("damage_deposit", "0")))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _bump_deposit_attempts(booking: Booking, *, when: datetime) -> int:
    attempt_number = (booking.deposit_attempt_count or 0) + 1
    Booking.objects.filter(pk=booking.id).update(
        deposit_attempt_count=attempt_number,
        updated_at=when,
    )
    booking.deposit_attempt_count = attempt_number
    return attempt_number


@shared_task(name="bookings.authorize_deposit_for_start_day")
def authorize_deposit_for_start_day(booking_id: int) -> bool:
    """
    Confirm (authorize) the deposit hold for a paid booking on its start date.
    """
    booking = Booking.objects.select_related("renter").filter(pk=booking_id).first()
    if booking is None:
        return False

    today = timezone.localdate()
    if (
        booking.status != Booking.Status.PAID
        or booking.is_terminal()
        or booking.start_date != today
        or booking.deposit_authorized_at is not None
    ):
        return False

    damage_deposit = _deposit_amount(booking)
    if damage_deposit <= Decimal("0"):
        now = timezone.now()
        Booking.objects.filter(pk=booking.id).update(
            deposit_authorized_at=now,
            updated_at=now,
        )
        try:
            create_owner_transfer_for_booking(
                booking=booking,
                payment_intent_id=booking.charge_payment_intent_id or "",
            )
        except StripeTransientError:
            logger.exception(
                "Owner transfer encountered transient error post-deposit for booking %s",
                booking.id,
            )
        except StripeConfigurationError:
            logger.exception(
                (
                    "Owner transfer skipped due to Stripe configuration error "
                    "post-deposit for booking %s"
                ),
                booking.id,
            )
        except StripePaymentError:
            logger.exception(
                "Owner transfer failed permanently post-deposit for booking %s",
                booking.id,
            )
        return True

    customer_id = (
        booking.renter_stripe_customer_id
        or getattr(booking.renter, "stripe_customer_id", "")  # type: ignore[attr-defined]
        or ""
    ).strip()
    payment_method_id = (booking.renter_stripe_payment_method_id or "").strip()
    if not customer_id or not payment_method_id:
        logger.info(
            "authorize_deposit_for_start_day: missing payment details for booking %s",
            booking.id,
        )
        return False

    now = timezone.now()
    attempt_number = _bump_deposit_attempts(booking, when=now)

    try:
        deposit_intent_id = create_booking_deposit_hold_intent(
            booking=booking,
            customer_id=customer_id,
            payment_method_id=payment_method_id,
        )
    except DepositAuthorizationInsufficientFunds:
        if attempt_number == 1:
            authorize_deposit_for_start_day.apply_async(args=[booking.id], countdown=3600)
            return False
        settle_and_cancel_for_deposit_failure(booking)
        return False
    except StripeTransientError:
        logger.warning(
            "Stripe transient error while authorizing deposit for booking %s",
            booking.id,
            exc_info=True,
        )
        return False
    except StripeConfigurationError:
        logger.exception(
            "Stripe configuration error while authorizing deposit for booking %s",
            booking.id,
        )
        return False
    except StripePaymentError as exc:
        logger.info(
            "Stripe payment error while authorizing deposit for booking %s: %s",
            booking.id,
            str(exc) or "payment error",
        )
        return False

    if deposit_intent_id:
        Booking.objects.filter(pk=booking.id).update(
            deposit_authorized_at=now,
            updated_at=now,
        )
        try:
            create_owner_transfer_for_booking(
                booking=booking,
                payment_intent_id=booking.charge_payment_intent_id or "",
            )
        except StripeTransientError:
            logger.exception(
                "Owner transfer encountered transient error post-deposit for booking %s",
                booking.id,
            )
        except StripeConfigurationError:
            logger.exception(
                (
                    "Owner transfer skipped due to Stripe configuration error "
                    "post-deposit for booking %s"
                ),
                booking.id,
            )
        except StripePaymentError:
            logger.exception(
                "Owner transfer failed permanently post-deposit for booking %s",
                booking.id,
            )
        return True
    return False


@shared_task(name="bookings.enqueue_deposit_authorizations")
def enqueue_deposit_authorizations() -> int:
    """
    Enqueue deposit authorization attempts for all paid bookings starting today.
    """
    today = timezone.localdate()
    enqueued = 0
    qs = Booking.objects.filter(
        status=Booking.Status.PAID,
        start_date=today,
        deposit_authorized_at__isnull=True,
        deposit_attempt_count__lte=0,
    ).select_related("renter")

    for booking in qs:
        if _deposit_amount(booking) <= Decimal("0"):
            continue
        authorize_deposit_for_start_day.delay(booking.id)
        enqueued += 1

    return enqueued
