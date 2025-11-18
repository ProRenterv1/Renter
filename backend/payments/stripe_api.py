"""Stripe payment helpers for booking transactions."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from bookings.models import Booking
from payments.ledger import log_transaction
from payments.models import Transaction

logger = logging.getLogger(__name__)
IDEMPOTENCY_VERSION = "v2"
User = get_user_model()


class StripeConfigurationError(Exception):
    """Stripe is not configured correctly in the environment."""


class StripeTransientError(Exception):
    """Temporary Stripe/API issue that should be retried."""


class StripePaymentError(Exception):
    """Permanent payment failure for a booking charge."""


def _get_stripe_api_key() -> str:
    """Return the configured Stripe API key or raise if missing."""
    api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    if not api_key:
        raise StripeConfigurationError("Stripe secret key not configured.")
    return api_key


def _to_cents(amount: Decimal) -> int:
    """Convert a Decimal dollar amount into integer cents."""
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(quantized * Decimal("100"))


def _parse_decimal(value: str | Decimal | None, field_name: str) -> Decimal:
    """Safely parse a string representation of a Decimal amount."""
    if value is None:
        raise StripePaymentError(f"Booking total '{field_name}' is missing.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StripePaymentError(f"Invalid booking total '{field_name}'.") from exc


def _handle_stripe_error(exc: stripe.error.StripeError) -> None:
    """Map Stripe SDK errors onto internal exception types."""
    if isinstance(exc, stripe.error.CardError):
        message = exc.user_message or "Your card was declined."
        raise StripePaymentError(message) from exc
    if isinstance(
        exc,
        (
            stripe.error.RateLimitError,
            stripe.error.APIConnectionError,
            stripe.error.APIError,
        ),
    ):
        raise StripeTransientError("Temporary Stripe error, please retry.") from exc
    if isinstance(exc, (stripe.error.AuthenticationError, stripe.error.PermissionError)):
        raise StripeConfigurationError("Stripe credentials are invalid or unauthorized.") from exc
    if isinstance(exc, stripe.error.InvalidRequestError):
        raise StripePaymentError(exc.user_message or "Invalid payment request.") from exc
    raise StripePaymentError(exc.user_message or "Stripe payment failure.") from exc


def _retrieve_payment_intent(intent_id: str, *, label: str) -> stripe.PaymentIntent | None:
    """Retrieve an existing PaymentIntent, returning None if it no longer exists."""
    if not intent_id:
        return None
    try:
        return stripe.PaymentIntent.retrieve(intent_id)
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") == "resource_missing":
            logger.info("Stripe PaymentIntent %s (%s) missing; will recreate.", label, intent_id)
            return None
        _handle_stripe_error(exc)
    except (
        stripe.error.RateLimitError,
        stripe.error.APIConnectionError,
        stripe.error.APIError,
    ) as exc:
        raise StripeTransientError(f"Temporary Stripe error retrieving {label} intent.") from exc
    return None


def create_booking_payment_intents(
    *,
    booking: Booking,
    customer_id: str,
    payment_method_id: str,
) -> tuple[str, str | None]:
    """
    Create or reuse PaymentIntents for a booking's rental charge and deposit.

    Returns:
        Tuple of (charge_intent_id, deposit_intent_id | None).
    """
    totals = booking.totals or {}
    total_charge = _parse_decimal(totals.get("total_charge"), "total_charge")
    damage_deposit = _parse_decimal(totals.get("damage_deposit", "0"), "damage_deposit")

    if damage_deposit < Decimal("0"):
        raise StripePaymentError("Damage deposit cannot be negative.")

    rental_charge = total_charge - damage_deposit
    if rental_charge <= Decimal("0"):
        raise StripePaymentError("Rental charge must be greater than zero.")

    stripe.api_key = _get_stripe_api_key()
    customer_value = customer_id or None
    if customer_value:
        _ensure_payment_method_for_customer(payment_method_id, customer_value)

    idempotency_base = f"booking:{booking.id}:{IDEMPOTENCY_VERSION}"
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"
    common_metadata = {
        "booking_id": str(booking.id),
        "listing_id": str(booking.listing_id),
        "env": env_label,
    }

    charge_intent = _retrieve_payment_intent(
        getattr(booking, "charge_payment_intent_id", ""),
        label="rental_charge",
    )

    if charge_intent is None:
        try:
            charge_intent = stripe.PaymentIntent.create(
                amount=_to_cents(rental_charge),
                currency="cad",
                payment_method_types=["card"],
                customer=customer_value,
                payment_method=payment_method_id,
                confirm=True,
                off_session=False,
                metadata={**common_metadata, "kind": "rental_charge"},
                idempotency_key=f"{idempotency_base}:charge",
            )
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    charge_intent_id = charge_intent.id

    deposit_intent_id: str | None = None
    if damage_deposit > Decimal("0"):
        deposit_intent = _retrieve_payment_intent(
            getattr(booking, "deposit_hold_id", ""),
            label="damage_deposit",
        )

        if deposit_intent is None:
            try:
                deposit_intent = stripe.PaymentIntent.create(
                    amount=_to_cents(damage_deposit),
                    currency="cad",
                    customer=customer_value,
                    payment_method=payment_method_id,
                    payment_method_types=["card"],
                    capture_method="manual",
                    confirm=True,
                    off_session=False,
                    metadata={**common_metadata, "kind": "damage_deposit"},
                    idempotency_key=f"{idempotency_base}:deposit",
                )
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

        deposit_intent_id = deposit_intent.id

    existing_charge_txn = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        stripe_payment_intent_id=charge_intent_id,
    ).first()

    if existing_charge_txn is None:
        log_transaction(
            user=booking.renter,
            kind=Transaction.Kind.BOOKING_CHARGE,
            direction=Transaction.Direction.DEBIT,
            amount=rental_charge,
            booking=booking,
            listing=booking.listing,
            description=f"Booking charge for listing {booking.listing_id}",
            stripe_payment_intent_id=charge_intent_id,
        )

    if damage_deposit > Decimal("0"):
        deposit_intent_identifier = deposit_intent_id or ""
        existing_deposit_txn = Transaction.objects.filter(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_HOLD,
            stripe_payment_intent_id=deposit_intent_identifier,
        ).first()

        if existing_deposit_txn is None:
            log_transaction(
                user=booking.renter,
                kind=Transaction.Kind.DAMAGE_DEPOSIT_HOLD,
                direction=Transaction.Direction.DEBIT,
                amount=damage_deposit,
                booking=booking,
                listing=booking.listing,
                description=f"Damage deposit hold for listing {booking.listing_id}",
                stripe_payment_intent_id=deposit_intent_identifier,
            )

    return charge_intent_id, deposit_intent_id


def ensure_stripe_customer(user: User, *, customer_id: str | None = None) -> str:
    """
    Return an existing Stripe Customer ID for the user, creating one if necessary.
    """
    stripe.api_key = _get_stripe_api_key()
    stored_id = (getattr(user, "stripe_customer_id", "") or "").strip()
    candidate_id = (customer_id or stored_id or "").strip()

    if candidate_id:
        try:
            stripe.Customer.retrieve(candidate_id)
        except stripe.error.InvalidRequestError:
            logger.info("Stripe customer %s missing; recreating.", candidate_id)
            candidate_id = ""
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    if not candidate_id:
        try:
            customer = stripe.Customer.create(
                email=user.email or None,
                name=(user.get_full_name() or user.username or f"user-{user.id}"),
                metadata={"user_id": str(user.id)},
            )
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)
        candidate_id = customer.id

    if candidate_id and candidate_id != stored_id:
        user.stripe_customer_id = candidate_id
        user.save(update_fields=["stripe_customer_id"])

    return candidate_id


def _ensure_payment_method_for_customer(payment_method_id: str, customer_id: str) -> None:
    """Attach the payment method to the Stripe customer if not already linked."""
    if not payment_method_id or not customer_id:
        return
    stripe.api_key = _get_stripe_api_key()
    try:
        payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)
    attached_customer = getattr(payment_method, "customer", None)
    if attached_customer == customer_id:
        return
    if attached_customer and attached_customer != customer_id:
        try:
            stripe.PaymentMethod.detach(payment_method_id)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)
    try:
        stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)


@api_view(["POST"])
@authentication_classes([])
@permission_classes([])
def stripe_webhook(request):
    """Handle Stripe webhook callbacks for booking-related PaymentIntents."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    endpoint_secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=endpoint_secret,
        )
    except ValueError:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    except stripe.error.SignatureVerificationError:
        return Response(status=status.HTTP_400_BAD_REQUEST)

    event_type = event.get("type")
    data_object = event.get("data", {}).get("object", {}) or {}
    metadata = data_object.get("metadata") or {}
    booking_id = metadata.get("booking_id")
    kind = metadata.get("kind")

    if event_type == "payment_intent.succeeded" and booking_id and kind == "rental_charge":
        try:
            booking = Booking.objects.get(pk=int(booking_id))
        except (Booking.DoesNotExist, ValueError):
            return Response(status=status.HTTP_200_OK)

        if booking.status in {Booking.Status.REQUESTED, Booking.Status.CONFIRMED}:
            intent_id = data_object.get("id", "") or booking.charge_payment_intent_id
            booking.status = Booking.Status.PAID
            booking.charge_payment_intent_id = intent_id or booking.charge_payment_intent_id
            booking.save(update_fields=["status", "charge_payment_intent_id", "updated_at"])

    return Response(status=status.HTTP_200_OK)
