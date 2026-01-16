"""Apply cancellation settlements via Stripe + ledger logging."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Sum

from bookings.models import Booking
from payments.ledger import log_transaction
from payments.models import Transaction
from payments.stripe_api import (
    _available_on_from_transfer,
    _get_stripe_api_key,
    _handle_stripe_error,
    _to_cents,
)
from payments_cancellation_policy import CancellationSettlement

logger = logging.getLogger(__name__)
User = get_user_model()
_ZERO = Decimal("0.00")


def _ensure_stripe_key() -> None:
    """Ensure the global Stripe API key is configured before SDK calls."""
    stripe.api_key = _get_stripe_api_key()


def _safe_decimal(value: object, default: Decimal = _ZERO) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


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

    owner_target = max(settlement.owner_delta, _ZERO)
    owner_total = (
        Transaction.objects.filter(
            user=owner,
            booking=booking,
            kind=Transaction.Kind.OWNER_EARNING,
        )
        .aggregate(total=Sum("amount"))
        .get("total")
        or _ZERO
    )
    owner_total = _safe_decimal(owner_total, _ZERO)
    owner_adjustment = owner_target - owner_total

    if owner_adjustment != _ZERO:
        owner_stripe_id: str | None = None
        owner_stripe_available_on = None
        if owner_adjustment < _ZERO:
            transfer_txn = (
                Transaction.objects.filter(
                    user=owner,
                    booking=booking,
                    kind=Transaction.Kind.OWNER_EARNING,
                    amount__gt=0,
                )
                .exclude(stripe_id__isnull=True)
                .exclude(stripe_id="")
                .order_by("created_at")
                .first()
            )
            if transfer_txn and transfer_txn.stripe_id:
                _ensure_stripe_key()
                try:
                    reversal = stripe.Transfer.create_reversal(
                        transfer_txn.stripe_id,
                        amount=_to_cents(abs(owner_adjustment)),
                    )
                    owner_stripe_id = getattr(reversal, "id", None) or (
                        reversal.get("id") if hasattr(reversal, "get") else None
                    )
                except stripe.error.InvalidRequestError as exc:
                    if getattr(exc, "code", "") == "resource_missing":
                        logger.info(
                            "Stripe transfer %s missing for booking %s; assuming reversed.",
                            transfer_txn.stripe_id,
                            booking.id,
                        )
                    else:
                        _handle_stripe_error(exc)
                except stripe.error.StripeError as exc:
                    _handle_stripe_error(exc)
            else:
                logger.warning(
                    "Owner payout adjustment missing transfer id for booking %s",
                    booking.id,
                )
        else:
            payout_account = getattr(owner, "payout_account", None)
            if (
                payout_account
                and payout_account.stripe_account_id
                and payout_account.payouts_enabled
            ):
                _ensure_stripe_key()
                try:
                    transfer = stripe.Transfer.create(
                        amount=_to_cents(owner_adjustment),
                        currency="cad",
                        destination=payout_account.stripe_account_id,
                        description=f"Owner payout adjustment for booking #{booking.id}",
                        metadata={
                            "kind": "owner_payout_adjustment",
                            "booking_id": str(booking.id),
                        },
                        transfer_group=f"booking:{booking.id}:owner_payout_adjustment",
                        idempotency_key=(
                            f"booking:{booking.id}:owner_payout_adjustment:"
                            f"{_to_cents(owner_adjustment)}"
                        ),
                    )
                    owner_stripe_id = getattr(transfer, "id", None) or (
                        transfer.get("id") if hasattr(transfer, "get") else None
                    )
                    owner_stripe_available_on = _available_on_from_transfer(transfer)
                except stripe.error.StripeError as exc:
                    _handle_stripe_error(exc)
            else:
                logger.warning(
                    "Owner payout adjustment skipped; missing Stripe account or payouts disabled.",
                    extra={"booking_id": booking.id, "owner_id": getattr(owner, "id", None)},
                )

        log_transaction(
            user=owner,
            booking=booking,
            kind=Transaction.Kind.OWNER_EARNING,
            amount=owner_adjustment,
            stripe_id=owner_stripe_id,
            stripe_available_on=owner_stripe_available_on,
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
