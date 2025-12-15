"""Domain helpers for booking validation and state transitions."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Optional

import stripe
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from listings.models import Listing
from notifications import tasks as notification_tasks
from payments.ledger import log_transaction
from payments.models import Transaction
from payments.stripe_api import (
    _get_stripe_api_key,
    _handle_stripe_error,
    _to_cents,
    ensure_connect_account,
)

from .models import Booking, BookingPhoto

logger = logging.getLogger(__name__)

# Statuses that block dates for availability and conflict detection.
# Plain requested bookings remain allowed to overlap.
ACTIVE_BOOKING_STATUSES = (
    Booking.Status.CONFIRMED,
    Booking.Status.PAID,
)

CancelActor = Literal["renter", "owner", "system", "no_show"]


def days_until_start(today: date, booking: Booking) -> int:
    """Return (booking.start_date - today).days."""
    if not booking.start_date:
        return 0
    return (booking.start_date - today).days


def is_overdue(today: date, booking: Booking) -> bool:
    """
    Return True if booking is overdue:
    today strictly greater than end_date (end-exclusive).
    """
    if not booking.end_date:
        return False
    return today > booking.end_date


def validate_booking_dates(start_date: date | None, end_date: date | None) -> None:
    """Validate that the provided dates exist and form a valid range."""
    if not start_date or not end_date:
        raise ValidationError({"non_field_errors": ["Start and end dates are required."]})
    if start_date >= end_date:
        raise ValidationError({"end_date": ["End date must be after start date."]})


def ensure_no_conflict(
    listing: Listing,
    start_date: date,
    end_date: date,
    *,
    exclude_booking_id: Optional[int] = None,
) -> None:
    """Ensure there are no overlapping bookings for the listing."""
    qs = Booking.objects.filter(listing=listing, status__in=ACTIVE_BOOKING_STATUSES)
    if exclude_booking_id is not None:
        qs = qs.exclude(pk=exclude_booking_id)
    conflicts = qs.filter(start_date__lt=end_date, end_date__gt=start_date)
    if conflicts.exists():
        raise ValidationError(
            {"non_field_errors": ["Requested dates are not available for this listing."]}
        )


def assert_can_confirm(booking: Booking) -> None:
    """Ensure the booking can be confirmed."""
    if booking.status != Booking.Status.REQUESTED:
        raise ValidationError({"status": ["Only requested bookings can be confirmed."]})


def assert_can_cancel(booking: Booking, actor: CancelActor | None = None) -> None:
    """
    Ensure the booking can be canceled given the actor.
    - Only requested/confirmed/paid may be canceled.
    - Completed/canceled cannot be canceled again.
    - Actor-specific rules can be tightened later.
    """
    if booking.status not in {
        Booking.Status.REQUESTED,
        Booking.Status.CONFIRMED,
        Booking.Status.PAID,
    }:
        raise ValidationError(
            {"status": ["Only requested, confirmed, or paid bookings can be canceled."]}
        )
    if actor is not None and actor not in {"renter", "owner", "system", "no_show"}:
        raise ValidationError({"non_field_errors": ["Invalid cancel actor."]})


def assert_can_complete(booking: Booking) -> None:
    """Ensure the booking can be marked as complete."""
    if booking.status not in {Booking.Status.CONFIRMED, Booking.Status.PAID}:
        raise ValidationError({"status": ["Only confirmed or paid bookings can be completed."]})
    if booking.status == Booking.Status.PAID and not booking.return_confirmed_at:
        raise ValidationError(
            {"return_confirmed_at": ["Owner must confirm return before completing the booking."]}
        )


def assert_can_confirm_pickup(booking: Booking) -> None:
    """
    Ensure the booking is in a state where owner can confirm pickup.
    """
    if booking.status != Booking.Status.PAID:
        raise ValidationError({"status": ["Only paid bookings can be confirmed as picked up."]})
    if booking.is_terminal():
        raise ValidationError({"status": ["This booking is not active."]})
    if booking.before_photos_required and not booking.before_photos_uploaded_at:
        raise ValidationError(
            {"non_field_errors": ["Before photos must be uploaded before confirming pickup."]}
        )
    if booking.before_photos_required:
        has_clean_before = BookingPhoto.objects.filter(
            booking=booking,
            role=BookingPhoto.Role.BEFORE,
            status=BookingPhoto.Status.ACTIVE,
            av_status=BookingPhoto.AVStatus.CLEAN,
        ).exists()
        if not has_clean_before:
            raise ValidationError(
                {
                    "non_field_errors": [
                        "At least one clean 'before' photo is required before pickup confirmation."
                    ]
                }
            )


def is_pre_payment(booking: Booking) -> bool:
    """
    Return True if the booking has no associated charge intent yet.
    """
    return not (getattr(booking, "charge_payment_intent_id", "") or "").strip()


def extra_days_for_late(today: date, booking: Booking, *, max_days: int = 2) -> int:
    """
    Return clamped extra days to charge for a late return.

    When the booking is overdue, clamp the number of late days to [1, max_days].
    """
    if not booking.end_date or max_days <= 0:
        return 0
    if not is_overdue(today, booking):
        return 0
    days_late = max((today - booking.end_date).days, 0)
    if days_late <= 0:
        return 0
    return max(1, min(days_late, max_days))


def is_severely_overdue(today: date, booking: Booking, *, threshold_days: int = 2) -> bool:
    """Return True when the booking has been overdue for at least threshold_days."""
    if not booking.end_date:
        return False
    if threshold_days <= 0:
        threshold_days = 0
    days_late = (today - booking.end_date).days
    return days_late >= threshold_days


def is_return_initiated(booking: Booking) -> bool:
    """
    True when the renter has indicated return (and optionally uploaded after photos),
    but the owner has not yet confirmed.
    """
    return (
        booking.status == Booking.Status.PAID
        and booking.pickup_confirmed_at is not None
        and booking.returned_by_renter_at is not None
        and booking.return_confirmed_at is None
    )


def is_return_completed(booking: Booking) -> bool:
    """
    True when the owner has confirmed the return (status is still PAID or COMPLETED).
    """
    return booking.return_confirmed_at is not None


def is_in_dispute_window(booking: Booking, *, now: datetime | None = None) -> bool:
    """
    True if a dispute window is defined and has not expired yet.
    This will be used later for dispute flows.
    """
    if booking.dispute_window_expires_at is None:
        return False
    if now is None:
        now = timezone.now()
    return now < booking.dispute_window_expires_at


def mark_canceled(
    booking: Booking,
    *,
    actor: CancelActor,
    auto: bool,
    reason: str | None = None,
) -> None:
    """
    Mutate the provided booking instance into a canceled state.
    """
    booking.status = Booking.Status.CANCELED
    booking.canceled_by = actor
    if reason:
        booking.canceled_reason = reason
    booking.auto_canceled = auto


def settle_and_cancel_for_deposit_failure(booking: Booking) -> None:
    """
    Cancel a booking and settle funds when deposit authorization fails twice.
    Refund 50% to renter, pay 30% to owner, keep 20% for platform.
    """

    if booking.status == Booking.Status.CANCELED:
        return

    totals = booking.totals or {}

    def _safe_decimal(value) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    def _money(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    rental_subtotal = _money(_safe_decimal(totals.get("rental_subtotal", "0")))
    service_fee_value = totals.get("service_fee", totals.get("renter_fee", "0"))
    service_fee = _money(_safe_decimal(service_fee_value))
    charge_amount = _money(rental_subtotal + service_fee)

    reason = "Insufficient funds for damage deposit"
    refund_amount = _money(charge_amount * Decimal("0.5"))
    owner_amount = _money(charge_amount * Decimal("0.3"))
    platform_amount = _money(charge_amount - refund_amount - owner_amount)

    charge_intent_id = (booking.charge_payment_intent_id or "").strip()

    stripe.api_key = _get_stripe_api_key()

    refund_id: str | None = None
    if charge_intent_id and refund_amount > Decimal("0"):
        try:
            refund = stripe.Refund.create(
                payment_intent=charge_intent_id,
                amount=_to_cents(refund_amount),
                idempotency_key=(
                    f"booking:{booking.id}:deposit_fail:refund:{_to_cents(refund_amount)}"
                ),
            )
            refund_id = getattr(refund, "id", None)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    owner_transfer_id: str | None = None
    if owner_amount > Decimal("0"):
        owner = getattr(booking, "owner", None)
        if owner:
            payout_account = ensure_connect_account(owner)
            if payout_account.stripe_account_id and payout_account.payouts_enabled:
                try:
                    transfer = stripe.Transfer.create(
                        amount=_to_cents(owner_amount),
                        currency="cad",
                        destination=payout_account.stripe_account_id,
                        description=f"Deposit failure payout for booking #{booking.id}",
                        metadata={
                            "kind": "owner_payout_deposit_failure",
                            "booking_id": str(booking.id),
                            "listing_id": str(booking.listing_id),
                        },
                        transfer_group=f"booking:{booking.id}:deposit_failure",
                        idempotency_key=(
                            f"booking:{booking.id}:deposit_fail:owner:{_to_cents(owner_amount)}"
                        ),
                    )
                    owner_transfer_id = getattr(transfer, "id", None)
                except stripe.error.StripeError as exc:
                    _handle_stripe_error(exc)

    with transaction.atomic():
        mark_canceled(booking, actor="system", auto=True, reason=reason)
        booking.save(
            update_fields=[
                "status",
                "canceled_by",
                "canceled_reason",
                "auto_canceled",
                "updated_at",
            ]
        )

        if refund_amount > Decimal("0"):
            log_transaction(
                user=booking.renter,
                booking=booking,
                kind=Transaction.Kind.REFUND,
                amount=refund_amount,
                stripe_id=refund_id or charge_intent_id or None,
            )

        if owner_amount > Decimal("0") and owner_transfer_id:
            owner = booking.owner
            log_transaction(
                user=owner,
                booking=booking,
                kind=Transaction.Kind.OWNER_EARNING,
                amount=owner_amount,
                stripe_id=owner_transfer_id,
            )

        if platform_amount > Decimal("0"):
            from payments_refunds import get_platform_ledger_user

            platform_user = get_platform_ledger_user()
            if platform_user:
                log_transaction(
                    user=platform_user,
                    booking=booking,
                    kind=Transaction.Kind.PLATFORM_FEE,
                    amount=platform_amount,
                )

    try:
        notification_tasks.send_deposit_failed_renter.delay(booking.id, f"{refund_amount:.2f}")
    except Exception:
        logger.info(
            "notifications: failed to queue deposit_failed_renter for booking %s", booking.id
        )
    try:
        notification_tasks.send_deposit_failed_owner.delay(booking.id, f"{owner_amount:.2f}")
    except Exception:
        logger.info(
            "notifications: failed to queue deposit_failed_owner for booking %s", booking.id
        )
