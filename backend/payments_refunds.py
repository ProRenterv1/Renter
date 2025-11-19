"""Apply cancellation settlements via Stripe + ledger logging."""

from __future__ import annotations

import logging
from decimal import Decimal

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model

from bookings.models import Booking
from payments.ledger import log_transaction
from payments.models import Transaction
from payments.stripe_api import _get_stripe_api_key, _handle_stripe_error, _to_cents
from payments_cancellation_policy import CancellationSettlement

logger = logging.getLogger(__name__)
User = get_user_model()


def _ensure_stripe_key() -> None:
    """Ensure the global Stripe API key is configured before SDK calls."""
    stripe.api_key = _get_stripe_api_key()


def get_platform_ledger_user() -> User | None:
    """Return the configured platform ledger user (if any)."""
    user_id = getattr(settings, "PLATFORM_LEDGER_USER_ID", None)
    if not user_id:
        return None
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("Configured PLATFORM_LEDGER_USER_ID=%s not found.", user_id)
    return None


def apply_cancellation_settlement(booking: Booking, settlement: CancellationSettlement) -> None:
    """Execute Stripe refunds/deposit actions and log all ledger entries."""

    renter = booking.renter
    owner = booking.owner

    refund_id: str | None = None
    if settlement.refund_to_renter > Decimal("0"):
        intent_id = (booking.charge_payment_intent_id or "").strip()
        if intent_id:
            _ensure_stripe_key()
            try:
                refund = stripe.Refund.create(
                    payment_intent=intent_id,
                    amount=_to_cents(settlement.refund_to_renter),
                )
                refund_id = refund.id
            except stripe.error.InvalidRequestError as exc:
                if getattr(exc, "code", "") == "resource_missing":
                    # Treat missing intents as already refunded (idempotent behavior).
                    logger.info(
                        "Stripe charge PaymentIntent %s missing for booking %s; assuming refunded.",
                        intent_id,
                        booking.id,
                    )
                else:
                    _handle_stripe_error(exc)
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

        log_transaction(
            user=renter,
            booking=booking,
            kind=Transaction.Kind.REFUND,
            amount=settlement.refund_to_renter,
            stripe_id=refund_id or intent_id or None,
        )

    deposit_hold_id = (booking.deposit_hold_id or "").strip()
    if settlement.deposit_capture_amount > Decimal("0"):
        if deposit_hold_id:
            _ensure_stripe_key()
            try:
                capture_intent = stripe.PaymentIntent.capture(
                    deposit_hold_id,
                    amount_to_capture=_to_cents(settlement.deposit_capture_amount),
                )
                deposit_hold_id = capture_intent.id
            except stripe.error.InvalidRequestError as exc:
                if getattr(exc, "code", "") == "resource_missing":
                    logger.info(
                        "Stripe deposit PaymentIntent %s missing for "
                        "booking %s; treat capture as noop.",
                        deposit_hold_id,
                        booking.id,
                    )
                else:
                    _handle_stripe_error(exc)
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)
        log_transaction(
            user=renter,
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
            amount=settlement.deposit_capture_amount,
            stripe_id=deposit_hold_id or None,
        )

    if settlement.deposit_release_amount > Decimal("0"):
        if deposit_hold_id and settlement.deposit_capture_amount == Decimal("0"):
            # Release holds by canceling the PaymentIntent when nothing was captured.
            _ensure_stripe_key()
            try:
                release_intent = stripe.PaymentIntent.cancel(deposit_hold_id)
                deposit_hold_id = release_intent.id
            except stripe.error.InvalidRequestError as exc:
                if getattr(exc, "code", "") == "resource_missing":
                    logger.info(
                        "Stripe deposit PaymentIntent %s already released for booking %s.",
                        deposit_hold_id,
                        booking.id,
                    )
                else:
                    _handle_stripe_error(exc)
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)
        log_transaction(
            user=renter,
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
            amount=settlement.deposit_release_amount,
            stripe_id=deposit_hold_id or None,
        )

    if settlement.owner_delta != Decimal("0"):
        log_transaction(
            user=owner,
            booking=booking,
            kind=Transaction.Kind.OWNER_EARNING,
            amount=settlement.owner_delta,
        )

    if settlement.platform_delta != Decimal("0"):
        platform_user = get_platform_ledger_user()
        if platform_user is not None:
            log_transaction(
                user=platform_user,
                booking=booking,
                kind=Transaction.Kind.PLATFORM_FEE,
                amount=settlement.platform_delta,
            )
        else:
            # Platform ledger user/account is not modeled yet; skip logging until configured.
            logger.info(
                "Platform delta %s for booking %s not logged; platform accounting pending.",
                settlement.platform_delta,
                booking.id,
            )
