"""Stripe payment helpers for booking transactions."""

from __future__ import annotations

import logging
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from bookings.models import Booking
from payments.ledger import log_transaction
from payments.models import OwnerPayoutAccount, Transaction

logger = logging.getLogger(__name__)
IDEMPOTENCY_VERSION = "v2"
AUTOMATIC_PAYMENT_METHODS_CONFIG = {"enabled": True, "allow_redirects": "never"}
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
    """Convert Decimal dollars to integer cents, rounding to the nearest cent."""
    cents = (amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(cents)


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


def _account_object_value(account_data: Any, field: str, default: Any = None) -> Any:
    """Safely fetch a field from a Stripe account object or dict payload."""
    if isinstance(account_data, dict):
        return account_data.get(field, default)
    return getattr(account_data, field, default)


def _listify(value: Any) -> list[Any]:
    """Convert requirement entries into a JSON-serializable list."""
    if value in (None, "", ()):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, (str, bytes)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _serialize_account_requirements(account_data: Any) -> dict[str, Any]:
    """Extract the requirements sub-structure from a Stripe account payload."""
    requirements = _account_object_value(account_data, "requirements", {}) or {}

    def _req_value(field: str, default: Any) -> Any:
        if isinstance(requirements, dict):
            return requirements.get(field, default) or default
        return getattr(requirements, field, default) or default

    return {
        "currently_due": _listify(_req_value("currently_due", [])),
        "eventually_due": _listify(_req_value("eventually_due", [])),
        "past_due": _listify(_req_value("past_due", [])),
        "disabled_reason": _req_value("disabled_reason", ""),
    }


def _sync_payout_account_from_stripe(
    payout_account: OwnerPayoutAccount,
    account_data: Any,
) -> OwnerPayoutAccount:
    """Update persisted payout account fields from a Stripe account payload."""
    account_id = _account_object_value(account_data, "id", payout_account.stripe_account_id)
    if account_id:
        payout_account.stripe_account_id = account_id
    charges_enabled = bool(_account_object_value(account_data, "charges_enabled", False))
    payouts_enabled = bool(_account_object_value(account_data, "payouts_enabled", False))
    requirements_due = _serialize_account_requirements(account_data)
    disabled_reason = requirements_due.get("disabled_reason")

    payout_account.charges_enabled = charges_enabled
    payout_account.payouts_enabled = payouts_enabled
    payout_account.requirements_due = requirements_due
    payout_account.is_fully_onboarded = bool(
        charges_enabled and payouts_enabled and not disabled_reason
    )
    payout_account.last_synced_at = timezone.now()
    payout_account.save()
    return payout_account


def ensure_connect_account(user: User) -> OwnerPayoutAccount:
    """Ensure the owner has a Stripe Connect Express account and sync it locally."""
    stripe.api_key = _get_stripe_api_key()

    try:
        payout_account = user.payout_account
        existing_account_id = payout_account.stripe_account_id or ""
    except OwnerPayoutAccount.DoesNotExist:
        payout_account = None
        existing_account_id = ""

    account_data: Any | None = None
    if existing_account_id:
        try:
            account_data = stripe.Account.retrieve(existing_account_id)
        except stripe.error.InvalidRequestError as exc:
            if getattr(exc, "code", "") == "resource_missing":
                logger.info(
                    "Stripe Connect account %s missing for user %s; recreating.",
                    existing_account_id,
                    user.id,
                )
            else:
                _handle_stripe_error(exc)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    if account_data is None:
        try:
            account_data = stripe.Account.create(
                type="express",
                country="CA",
                capabilities={
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                business_type="individual",
                metadata={"user_id": str(user.id)},
            )
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    if payout_account is None:
        payout_account = OwnerPayoutAccount(
            user=user,
            stripe_account_id=_account_object_value(account_data, "id", ""),
        )

    return _sync_payout_account_from_stripe(payout_account, account_data)


def _get_frontend_origin() -> str:
    """Return the configured frontend origin or a local fallback."""
    configured = (getattr(settings, "FRONTEND_ORIGIN", "") or "").strip()
    base = configured or "http://localhost:5173"
    return base.rstrip("/") or base


def create_connect_onboarding_link(user: User) -> str:
    """Create a Stripe Connect onboarding link for the owner."""
    payout_account = ensure_connect_account(user)
    stripe.api_key = _get_stripe_api_key()

    base_origin = _get_frontend_origin()
    refresh_url = f"{base_origin}/owner/payouts?onboarding=refresh"
    return_url = f"{base_origin}/owner/payouts?onboarding=return"

    try:
        link = stripe.AccountLink.create(
            account=payout_account.stripe_account_id,
            type="account_onboarding",
            refresh_url=refresh_url,
            return_url=return_url,
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    link_url = getattr(link, "url", None) or link.get("url")  # type: ignore[arg-type]
    if not link_url:
        raise StripeConfigurationError("Stripe did not return an onboarding link.")
    return link_url


def _handle_connect_account_updated_event(account_payload: Any) -> None:
    """Sync OwnerPayoutAccount rows based on Stripe account.updated data."""
    stripe_account_id = _account_object_value(account_payload, "id", "")
    if not stripe_account_id:
        return

    payout_account = OwnerPayoutAccount.objects.filter(
        stripe_account_id=stripe_account_id,
    ).first()

    if payout_account is None:
        metadata = _account_object_value(account_payload, "metadata", {}) or {}
        if isinstance(metadata, dict):
            metadata_dict = metadata
        elif hasattr(metadata, "items"):
            metadata_dict = dict(metadata.items())
        else:
            metadata_dict = {}
        user_id = metadata_dict.get("user_id")
        if not user_id:
            return
        try:
            user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            return
        payout_account, _ = OwnerPayoutAccount.objects.get_or_create(
            user=user,
            defaults={"stripe_account_id": stripe_account_id},
        )

    _sync_payout_account_from_stripe(payout_account, account_payload)


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
    rental_subtotal = _parse_decimal(totals.get("rental_subtotal"), "rental_subtotal")
    service_fee = _parse_decimal(
        totals.get("service_fee", totals.get("renter_fee", "0")),
        "service_fee",
    )
    damage_deposit = _parse_decimal(totals.get("damage_deposit", "0"), "damage_deposit")

    if damage_deposit < Decimal("0"):
        raise StripePaymentError("Damage deposit cannot be negative.")

    charge_amount = rental_subtotal + service_fee
    if charge_amount <= Decimal("0"):
        raise StripePaymentError("Rental charge must be greater than zero.")
    charge_amount_cents = _to_cents(charge_amount)

    stripe.api_key = _get_stripe_api_key()
    customer_value = (
        customer_id or getattr(booking.renter, "stripe_customer_id", "") or ""
    ).strip() or None
    if customer_value and payment_method_id:
        _ensure_payment_method_for_customer(payment_method_id, customer_value)

    idempotency_base = f"booking:{booking.id}:{IDEMPOTENCY_VERSION}"
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"
    common_metadata = {
        "booking_id": str(booking.id),
        "listing_id": str(booking.listing_id),
        "env": env_label,
    }
    currency = "cad"

    charge_intent = _retrieve_payment_intent(
        getattr(booking, "charge_payment_intent_id", ""),
        label="booking_charge",
    )

    if charge_intent is None:
        try:
            charge_intent = stripe.PaymentIntent.create(
                amount=charge_amount_cents,
                currency=currency,
                automatic_payment_methods={**AUTOMATIC_PAYMENT_METHODS_CONFIG},
                customer=customer_value,
                payment_method=payment_method_id or None,
                confirm=bool(payment_method_id),
                off_session=False,
                capture_method="automatic",
                metadata={**common_metadata, "kind": "booking_charge"},
                idempotency_key=f"{idempotency_base}:charge:{charge_amount_cents}",
            )
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    charge_intent_id = charge_intent.id

    deposit_field_name = None
    if hasattr(booking, "deposit_payment_intent_id"):
        deposit_field_name = "deposit_payment_intent_id"
    elif hasattr(booking, "deposit_hold_id"):
        deposit_field_name = "deposit_hold_id"

    deposit_intent_id: str | None = None
    if damage_deposit > Decimal("0"):
        existing_id = ""
        if deposit_field_name:
            existing_id = getattr(booking, deposit_field_name, "") or ""
        deposit_intent = _retrieve_payment_intent(
            existing_id,
            label="damage_deposit",
        )

        if deposit_intent is None:
            deposit_amount_cents = _to_cents(damage_deposit)
            try:
                deposit_intent = stripe.PaymentIntent.create(
                    amount=deposit_amount_cents,
                    currency=currency,
                    automatic_payment_methods={**AUTOMATIC_PAYMENT_METHODS_CONFIG},
                    customer=customer_value,
                    payment_method=payment_method_id or None,
                    confirm=bool(payment_method_id),
                    off_session=False,
                    capture_method="manual",
                    metadata={**common_metadata, "kind": "damage_deposit"},
                    idempotency_key=f"{idempotency_base}:deposit:{deposit_amount_cents}",
                )
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

        deposit_intent_id = deposit_intent.id

    booking.charge_payment_intent_id = charge_intent_id
    update_fields = ["charge_payment_intent_id"]
    if deposit_field_name:
        setattr(booking, deposit_field_name, deposit_intent_id or "")
        update_fields.append(deposit_field_name)
    booking.save(update_fields=update_fields)

    existing_charge_txn = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        stripe_id=charge_intent_id,
    ).first()

    if existing_charge_txn is None:
        log_transaction(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.BOOKING_CHARGE,
            amount=charge_amount,
            currency=currency,
            stripe_id=charge_intent_id,
        )

    if deposit_intent_id is not None:
        existing_deposit_txn = Transaction.objects.filter(
            user=booking.renter,
            booking=booking,
            kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
            stripe_id=deposit_intent_id,
        ).first()

        if existing_deposit_txn is None:
            log_transaction(
                user=booking.renter,
                booking=booking,
                kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
                amount=damage_deposit,
                currency=currency,
                stripe_id=deposit_intent_id,
            )

    return charge_intent_id, deposit_intent_id


def create_late_fee_payment_intent(
    *,
    booking: Booking,
    amount: Decimal,
    description: str = "Late return fee",
) -> str:
    """
    Create + confirm an additional PaymentIntent charging the renter for a late fee.
    Returns the PaymentIntent id.
    """
    if amount <= Decimal("0"):
        raise StripePaymentError("Late fee must be greater than zero.")

    stripe.api_key = _get_stripe_api_key()
    customer_id = (getattr(booking.renter, "stripe_customer_id", "") or "").strip()
    if not customer_id:
        raise StripeConfigurationError("Renter is missing a Stripe customer id.")

    cents = _to_cents(amount)
    idempotency_key = f"booking:{booking.id}:{IDEMPOTENCY_VERSION}:late:{cents}"
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"
    metadata = {
        "booking_id": str(booking.id),
        "listing_id": str(booking.listing_id),
        "env": env_label,
        "kind": "booking_late_fee",
    }

    try:
        intent = stripe.PaymentIntent.create(
            amount=cents,
            currency="cad",
            customer=customer_id,
            description=description,
            automatic_payment_methods={**AUTOMATIC_PAYMENT_METHODS_CONFIG},
            capture_method="automatic",
            confirm=True,
            off_session=True,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    log_transaction(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        amount=amount,
        stripe_id=intent.id,
    )
    return intent.id


def capture_deposit_amount(*, booking: Booking, amount: Decimal) -> str | None:
    """
    Capture part or all of the existing deposit PaymentIntent for this booking.
    Returns the PaymentIntent id (or None if no deposit hold).
    """
    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        return None
    if amount <= Decimal("0"):
        raise StripePaymentError("Deposit capture amount must be greater than zero.")

    stripe.api_key = _get_stripe_api_key()
    cents = _to_cents(amount)
    try:
        intent = stripe.PaymentIntent.capture(
            deposit_intent_id,
            amount_to_capture=cents,
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    log_transaction(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        amount=amount,
        stripe_id=deposit_intent_id,
    )
    return intent.id


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

    if event_type == "account.updated":
        _handle_connect_account_updated_event(data_object)
        return Response(status=status.HTTP_200_OK)

    if event_type == "payment_intent.succeeded" and booking_id and kind == "booking_charge":
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
