"""Settlement helpers for operator finance actions (refunds, deposit flows, awards)."""

from __future__ import annotations

import logging
from decimal import Decimal

import stripe
from django.conf import settings

from bookings.models import Booking
from payments.ledger import log_transaction
from payments.models import Transaction
from payments.stripe_api import StripePaymentError, _get_stripe_api_key, _handle_stripe_error
from payments.stripe_api import capture_deposit_amount as _capture_deposit_amount
from payments.stripe_api import ensure_connect_account
from payments.stripe_api import release_deposit_hold as _release_deposit_hold
from payments.tax import platform_gst_enabled, platform_gst_rate, split_tax_included
from payments_refunds import get_platform_ledger_user

logger = logging.getLogger(__name__)
TWO_PLACES = Decimal("0.01")


def _cents_to_decimal(cents: int | None) -> Decimal:
    cents_value = Decimal(cents or 0)
    return (cents_value / Decimal("100")).quantize(TWO_PLACES)


def refund_booking_charge(
    booking: Booking, amount_cents: int | None, dispute_id: str | int | None = None
) -> tuple[str | None, int | None]:
    """
    Create a Stripe refund for the booking charge and log the ledger entry.
    Safe for retries via idempotency key and duplicate-ledger guards.
    """
    intent_id = (getattr(booking, "charge_payment_intent_id", "") or "").strip()
    if not intent_id:
        raise StripePaymentError("Booking is missing the charge PaymentIntent id.")

    allowed_statuses = {
        Booking.Status.PAID,
        Booking.Status.COMPLETED,
        Booking.Status.CANCELED,
    }
    if booking.status not in allowed_statuses:
        raise StripePaymentError("Booking is not in a refundable state.")

    if amount_cents is not None and amount_cents <= 0:
        raise StripePaymentError("Refund amount must be greater than zero.")

    stripe.api_key = _get_stripe_api_key()

    refund = None
    refund_error_code = ""
    refund_id: str | None = None
    refunded_cents: int | None = None

    id_base = f"dispute:{dispute_id}" if dispute_id is not None else f"booking:{booking.id}"
    amount_key = amount_cents if amount_cents is not None else "full"
    idempotency_key = f"{id_base}:refund:{amount_key}"

    refund_kwargs = {"payment_intent": intent_id, "idempotency_key": idempotency_key}
    if amount_cents is not None:
        refund_kwargs["amount"] = int(amount_cents)

    try:
        refund = stripe.Refund.create(**refund_kwargs)
    except stripe.error.InvalidRequestError as exc:
        refund_error_code = getattr(exc, "code", "") or ""
        if refund_error_code in ("charge_already_refunded", "resource_missing"):
            logger.info(
                "Refund idempotent noop for booking %s (intent %s): %s",
                booking.id,
                intent_id,
                refund_error_code,
            )
        else:
            _handle_stripe_error(exc)
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    if refund is not None:
        refund_id = getattr(refund, "id", None) or (
            refund.get("id") if hasattr(refund, "get") else None
        )
        refunded_cents = getattr(refund, "amount", None) or (
            refund.get("amount") if hasattr(refund, "get") else None
        )

    if refunded_cents is None:
        refunded_cents = amount_cents

    if refunded_cents is None and refund_error_code != "resource_missing":
        try:
            intent = stripe.PaymentIntent.retrieve(intent_id)
            refunded_cents = getattr(intent, "amount_received", None) or getattr(
                intent, "amount", None
            )
        except stripe.error.InvalidRequestError as exc:
            if getattr(exc, "code", "") != "resource_missing":
                _handle_stripe_error(exc)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    if refunded_cents is None:
        raise StripePaymentError("Unable to determine refunded amount.")

    ledger_stripe_id = refund_id or intent_id
    existing_refund = Transaction.objects.filter(
        kind=Transaction.Kind.REFUND, stripe_id=ledger_stripe_id
    ).first()

    if existing_refund is None:
        log_transaction(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.REFUND,
            amount=_cents_to_decimal(refunded_cents),
            stripe_id=ledger_stripe_id,
        )

    return refund_id, refunded_cents


def capture_deposit_amount(
    booking: Booking, amount_cents: int, dispute_id: str | int | None = None
) -> tuple[str | None, int]:
    """
    Capture a specified amount from the booking's deposit hold.
    Safe on retries by checking ledger rows and PaymentIntent status first.
    """
    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        raise StripePaymentError("Booking is missing a deposit hold id.")
    if getattr(booking, "deposit_released_at", None):
        raise StripePaymentError("Deposit hold has already been released.")

    if booking.status not in (Booking.Status.PAID, Booking.Status.COMPLETED):
        raise StripePaymentError("Booking is not eligible for deposit capture.")

    if amount_cents is None or amount_cents <= 0:
        raise StripePaymentError("Capture amount must be greater than zero.")

    amount_decimal = _cents_to_decimal(amount_cents)
    existing_capture = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        stripe_id=deposit_intent_id,
        amount=amount_decimal,
    ).first()
    if existing_capture is not None:
        return deposit_intent_id, amount_cents

    stripe.api_key = _get_stripe_api_key()

    try:
        intent = stripe.PaymentIntent.retrieve(deposit_intent_id)
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") == "resource_missing":
            raise StripePaymentError("Deposit PaymentIntent no longer exists.") from exc
        _handle_stripe_error(exc)
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)
    else:
        status = getattr(intent, "status", "") or ""
        if status == "succeeded":
            captured_value = getattr(intent, "amount_received", None)
            captured_cents = int(captured_value) if captured_value is not None else amount_cents
            existing_txn = Transaction.objects.filter(
                user=booking.renter,
                booking=booking,
                kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
                stripe_id=deposit_intent_id,
            ).first()
            if existing_txn is None:
                log_transaction(
                    user=booking.renter,
                    booking=booking,
                    kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
                    amount=_cents_to_decimal(captured_cents),
                    stripe_id=deposit_intent_id,
                )
            return deposit_intent_id, captured_cents
        if status == "canceled":
            raise StripePaymentError("Deposit PaymentIntent is already canceled/released.")

    captured_intent_id = _capture_deposit_amount(booking=booking, amount=amount_decimal)
    return captured_intent_id or deposit_intent_id, amount_cents


def release_deposit_hold(booking: Booking, dispute_id: str | int | None = None) -> bool:
    """Release the deposit hold; wrapper remains retry-safe via underlying helper."""
    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        raise StripePaymentError("Booking is missing a deposit hold id.")

    _release_deposit_hold(booking)
    return True


def transfer_damage_award_to_owner(
    booking: Booking, amount_cents: int, dispute_id: str | int
) -> str:
    """
    Transfer a captured deposit amount to the owner via Stripe Connect.
    Logs owner earning (and platform fee when configured) idempotently.
    """
    if amount_cents is None or amount_cents <= 0:
        raise StripePaymentError("Transfer amount must be greater than zero.")

    if booking.status not in (Booking.Status.PAID, Booking.Status.COMPLETED):
        raise StripePaymentError("Booking is not eligible for damage award transfer.")

    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        raise StripePaymentError("Booking is missing a deposit hold id.")

    payout_account = ensure_connect_account(booking.owner)
    if not payout_account.stripe_account_id:
        raise StripePaymentError("Owner does not have a Stripe Connect account.")
    if not payout_account.charges_enabled:
        logger.warning(
            "Owner Connect account not charge-enabled for booking %s; proceeding with transfer.",
            booking.id,
        )

    stripe.api_key = _get_stripe_api_key()

    idempotency_key = f"dispute:{dispute_id}:booking:{booking.id}:damage_award:{int(amount_cents)}"
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"

    try:
        transfer = stripe.Transfer.create(
            amount=int(amount_cents),
            currency="cad",
            destination=payout_account.stripe_account_id,
            description=f"Damage deposit award for booking #{booking.id}",
            metadata={
                "kind": "damage_award",
                "booking_id": str(booking.id),
                "listing_id": str(getattr(booking, "listing_id", "")),
                "dispute_id": str(dispute_id),
                "deposit_hold_id": deposit_intent_id,
                "env": env_label,
            },
            transfer_group=f"booking:{booking.id}:damage_award",
            idempotency_key=idempotency_key,
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)
        raise

    transfer_id = getattr(transfer, "id", None) or (
        transfer.get("id") if hasattr(transfer, "get") else ""
    )

    owner_amount = _cents_to_decimal(amount_cents)
    existing_owner_txn = Transaction.objects.filter(
        user=booking.owner,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
        stripe_id=transfer_id,
    ).first()
    if existing_owner_txn is None:
        log_transaction(
            user=booking.owner,
            booking=booking,
            kind=Transaction.Kind.OWNER_EARNING,
            amount=owner_amount,
            stripe_id=transfer_id,
        )

    platform_user = get_platform_ledger_user()
    if platform_user is not None:
        if platform_gst_enabled():
            base, gst = split_tax_included(owner_amount, platform_gst_rate())
            existing_platform_txn = Transaction.objects.filter(
                user=platform_user,
                booking=booking,
                kind=Transaction.Kind.PLATFORM_FEE,
                stripe_id=transfer_id,
            ).first()
            if existing_platform_txn is None:
                log_transaction(
                    user=platform_user,
                    booking=booking,
                    kind=Transaction.Kind.PLATFORM_FEE,
                    amount=base,
                    stripe_id=transfer_id,
                )
            if gst > Decimal("0.00"):
                existing_gst_txn = Transaction.objects.filter(
                    user=platform_user,
                    booking=booking,
                    kind=Transaction.Kind.GST_COLLECTED,
                    stripe_id=transfer_id,
                ).first()
                if existing_gst_txn is None:
                    log_transaction(
                        user=platform_user,
                        booking=booking,
                        kind=Transaction.Kind.GST_COLLECTED,
                        amount=gst,
                        stripe_id=transfer_id,
                    )
        else:
            existing_platform_txn = Transaction.objects.filter(
                user=platform_user,
                booking=booking,
                kind=Transaction.Kind.PLATFORM_FEE,
                stripe_id=transfer_id,
            ).first()
            if existing_platform_txn is None:
                log_transaction(
                    user=platform_user,
                    booking=booking,
                    kind=Transaction.Kind.PLATFORM_FEE,
                    amount=owner_amount,
                    stripe_id=transfer_id,
                )

    return transfer_id
