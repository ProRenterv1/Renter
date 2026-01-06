"""Settlement helpers for operator dispute resolutions."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import stripe

from bookings.models import Booking
from payments.ledger import log_transaction
from payments.models import Transaction
from payments.stripe_api import StripePaymentError, _get_stripe_api_key, _handle_stripe_error
from payments.stripe_api import capture_deposit_amount as stripe_capture_deposit_amount
from payments.stripe_api import release_deposit_hold as stripe_release_deposit_hold

logger = logging.getLogger(__name__)
TWO_PLACES = Decimal("0.01")


def _to_decimal(amount_cents: int) -> Decimal:
    return (Decimal(amount_cents) / Decimal("100")).quantize(TWO_PLACES)


def refund_booking_charge(booking: Booking, amount_cents: int) -> Optional[str]:
    """
    Issue a Stripe refund against the booking charge.

    Idempotent via Stripe idempotency keys and ledger duplicate guards.
    Returns the Stripe refund id (if created) or None.
    """

    if amount_cents is None or amount_cents <= 0:
        raise StripePaymentError("Refund amount must be greater than zero.")

    intent_id = (getattr(booking, "charge_payment_intent_id", "") or "").strip()
    if not intent_id:
        raise StripePaymentError("Booking is missing the charge PaymentIntent id.")

    stripe.api_key = _get_stripe_api_key()
    idempotency_key = f"booking:{booking.id}:refund:{amount_cents}"
    refund = None
    try:
        refund = stripe.Refund.create(
            payment_intent=intent_id,
            amount=int(amount_cents),
            idempotency_key=idempotency_key,
        )
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") == "charge_already_refunded":
            logger.info("Refund already processed for booking %s", booking.id)
        else:
            _handle_stripe_error(exc)
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    refund_id = getattr(refund, "id", None) or (refund.get("id") if refund else None)
    ledger_amount = _to_decimal(amount_cents)

    existing = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.REFUND,
        amount=ledger_amount,
    )
    if refund_id:
        existing = existing.filter(stripe_id=refund_id)
    existing_txn = existing.first()
    if existing_txn is None:
        log_transaction(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.REFUND,
            amount=ledger_amount,
            stripe_id=refund_id or intent_id,
        )
    return refund_id


def capture_deposit_amount_cents(booking: Booking, amount_cents: int) -> Optional[str]:
    """Capture part of the deposit; safe for retries via ledger guard and Stripe idempotency."""

    if amount_cents is None or amount_cents <= 0:
        raise StripePaymentError("Capture amount must be greater than zero.")

    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        raise StripePaymentError("Booking is missing a deposit hold id.")

    amount_decimal = _to_decimal(amount_cents)
    existing = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        stripe_id=deposit_intent_id,
        amount=amount_decimal,
    ).first()
    if existing:
        return deposit_intent_id

    intent_id = stripe_capture_deposit_amount(booking=booking, amount=amount_decimal)
    return intent_id or deposit_intent_id


def release_deposit_hold_if_needed(booking: Booking) -> bool:
    """Release any remaining deposit hold; underlying helper is idempotent."""

    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        return False
    stripe_release_deposit_hold(booking)
    return True
