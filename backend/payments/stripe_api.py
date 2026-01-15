"""Stripe payment helpers for booking transactions."""

from __future__ import annotations

import contextvars
import logging
from datetime import date, datetime, timedelta
from datetime import timezone as datetime_timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, TypeVar

import stripe
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.response import Response

from bookings.models import Booking
from identity.models import IdentityVerification
from listings.models import Listing
from payments.ledger import log_transaction
from payments.models import OwnerPayoutAccount, PaymentSetupIntent, Transaction
from promotions.models import PromotedSlot, PromotionCheckoutSession

logger = logging.getLogger(__name__)
IDEMPOTENCY_VERSION = "v2"
AUTOMATIC_PAYMENT_METHODS_CONFIG = {"enabled": True, "allow_redirects": "never"}
CONNECT_ACCOUNT_EXPAND = ["individual", "external_accounts"]
CUSTOMER_VERIFY_TTL = timedelta(hours=12)
SETUP_INTENT_REFRESH_AGE = timedelta(minutes=10)
OPEN_SETUP_INTENT_STATUSES = {
    "requires_payment_method",
    "requires_action",
    "requires_confirmation",
    "processing",
}
CHECKOUT_SESSION_REFRESH_AGE = timedelta(minutes=5)
_CUSTOMER_CACHE: contextvars.ContextVar[dict[int, str]] = contextvars.ContextVar(
    "stripe_customer_cache",
    default=None,  # type: ignore[arg-type]
)
_PAYMENT_METHOD_CACHE: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "stripe_payment_method_cache",
    default=None,  # type: ignore[arg-type]
)
T = TypeVar("T")


def _log_stripe_call(kind: str, **extra: Any) -> None:
    logger.debug("stripe_call", extra={"kind": kind, **extra})


User = get_user_model()


class StripeConfigurationError(Exception):
    """Stripe is not configured correctly in the environment."""


class StripeTransientError(Exception):
    """Temporary Stripe/API issue that should be retried."""


class StripePaymentError(Exception):
    """Permanent payment failure for a booking charge."""


class DepositAuthorizationInsufficientFunds(StripePaymentError):
    """Raised when a deposit hold fails due to insufficient funds."""


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


def _extract_booking_fees(booking: Booking) -> dict[str, Decimal]:
    """Return parsed booking totals needed for payouts/fees."""
    totals = booking.totals or {}

    rental_subtotal = _parse_decimal(totals.get("rental_subtotal"), "rental_subtotal")
    renter_fee_raw = totals.get("renter_fee_total")
    if renter_fee_raw is None:
        renter_fee_raw = totals.get("renter_fee")
    if renter_fee_raw is None:
        renter_fee_raw = totals.get("service_fee")
    renter_fee = _parse_decimal(renter_fee_raw, "renter_fee")
    platform_fee_total_value = totals.get("platform_fee_total")
    platform_fee_total = (
        _parse_decimal(platform_fee_total_value, "platform_fee_total")
        if platform_fee_total_value is not None
        else None
    )
    owner_fee_raw = totals.get("owner_fee_total", totals.get("owner_fee"))
    if owner_fee_raw is None and platform_fee_total is not None:
        owner_fee = platform_fee_total - renter_fee
    else:
        owner_fee = _parse_decimal(owner_fee_raw, "owner_fee")
    if platform_fee_total is None:
        platform_fee_total = renter_fee + owner_fee

    owner_payout_value = totals.get("owner_payout")
    owner_payout = (
        _parse_decimal(owner_payout_value, "owner_payout")
        if owner_payout_value is not None
        else rental_subtotal - owner_fee
    )

    if rental_subtotal <= Decimal("0"):
        raise StripePaymentError("Booking rental_subtotal must be greater than zero.")
    if owner_payout < Decimal("0"):
        raise StripePaymentError("Booking owner_payout cannot be negative.")

    return {
        "rental_subtotal": rental_subtotal,
        "renter_fee": renter_fee,
        "owner_fee": owner_fee,
        "platform_fee_total": platform_fee_total,
        "owner_payout": owner_payout,
    }


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


def call_stripe_callable(
    fn: Callable[..., T],
    *,
    primary_kwargs: dict[str, Any],
    fallback_kwargs: dict[str, Any],
    error_keywords: tuple[str, ...] = ("cache_scope",),
) -> T:
    """
    Invoke a Stripe helper while tolerating monkeypatched stubs that don't accept
    newer optional keyword arguments (e.g., cache_scope).
    """
    try:
        return fn(**primary_kwargs)
    except TypeError as exc:
        if any(keyword in str(exc) for keyword in error_keywords):
            return fn(**fallback_kwargs)
        raise


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


def _cancel_payment_intent(intent_id: str) -> bool:
    """
    Cancel a PaymentIntent if the Stripe client exposes the cancel method.

    Returns True when a cancel was attempted and did not raise, False when the client
    does not support cancel (e.g., in lightweight test doubles).
    """
    cancel_fn = getattr(stripe.PaymentIntent, "cancel", None)
    if cancel_fn is None:
        logger.debug("stripe.PaymentIntent.cancel missing; skipping cancel for %s", intent_id)
        return False
    try:
        cancel_fn(intent_id)
        return True
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") != "resource_missing":
            _handle_stripe_error(exc)
    except stripe.error.StripeError as exc:  # noqa: PERF203
        _handle_stripe_error(exc)
    return False


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


def _extract_primary_bank_account(account_data: Any) -> Any | None:
    """Return the default bank account entry from a Stripe account payload."""
    external_accounts = _account_object_value(account_data, "external_accounts", {}) or {}
    accounts_list: list[Any] = []
    if isinstance(external_accounts, dict):
        accounts_list = external_accounts.get("data") or []
    elif hasattr(external_accounts, "data"):
        accounts_list = getattr(external_accounts, "data", []) or []
    else:
        try:
            accounts_list = list(external_accounts)
        except TypeError:
            accounts_list = []

    primary = None
    for acct in accounts_list:
        if _account_object_value(acct, "object", "") != "bank_account":
            continue
        if _account_object_value(acct, "default_for_currency", False):
            primary = acct
            break
        if primary is None:
            primary = acct
    return primary


def _sync_owner_profile_from_stripe(user: User, account_data: Any) -> None:
    """Update local profile fields from Stripe Connect individual details."""
    individual = _account_object_value(account_data, "individual", {}) or {}
    if not individual:
        return

    updated_fields: list[str] = []

    phone_raw = str(_account_object_value(individual, "phone", "") or "").strip()
    if phone_raw:
        normalized = phone_raw
        try:
            from users.serializers import normalize_phone

            normalized = normalize_phone(phone_raw)
        except Exception:
            normalized = phone_raw
        if normalized and normalized != getattr(user, "phone", None):
            if not User.objects.exclude(pk=user.pk).filter(phone=normalized).exists():
                user.phone = normalized
                updated_fields.append("phone")

    dob_data = _account_object_value(individual, "dob", {}) or {}
    dob_day = _account_object_value(dob_data, "day", None)
    dob_month = _account_object_value(dob_data, "month", None)
    dob_year = _account_object_value(dob_data, "year", None)
    if dob_day and dob_month and dob_year:
        try:
            dob_date = date(int(dob_year), int(dob_month), int(dob_day))
        except (TypeError, ValueError):
            dob_date = None
        if dob_date and dob_date != getattr(user, "birth_date", None):
            user.birth_date = dob_date
            updated_fields.append("birth_date")

    address = _account_object_value(individual, "address", {}) or {}
    line1 = str(_account_object_value(address, "line1", "") or "").strip()
    city = str(_account_object_value(address, "city", "") or "").strip()
    state = str(_account_object_value(address, "state", "") or "").strip()
    postal = str(_account_object_value(address, "postal_code", "") or "").strip()

    if line1 and line1 != getattr(user, "street_address", ""):
        user.street_address = line1
        updated_fields.append("street_address")
    if city and city != getattr(user, "city", ""):
        user.city = city
        updated_fields.append("city")

    province = state.upper() if state else ""
    if province and province != getattr(user, "province", ""):
        user.province = province
        updated_fields.append("province")

    postal_clean = postal.upper() if postal else ""
    if postal_clean and postal_clean != getattr(user, "postal_code", ""):
        user.postal_code = postal_clean
        updated_fields.append("postal_code")

    if updated_fields:
        user.save(update_fields=updated_fields)


def _sync_bank_details_from_stripe(
    payout_account: OwnerPayoutAccount,
    account_data: Any,
) -> None:
    """Copy the default external bank account details onto the payout_account record."""
    bank_account = _extract_primary_bank_account(account_data)
    if bank_account is None:
        return

    routing_number = str(_account_object_value(bank_account, "routing_number", "") or "").replace(
        " ",
        "",
    )
    if routing_number:
        if len(routing_number) >= 8:
            payout_account.institution_number = routing_number[:3]
            payout_account.transit_number = routing_number[3:8]

    last4 = str(_account_object_value(bank_account, "last4", "") or "").strip()
    if last4:
        payout_account.account_number = last4


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
    business_type = (_account_object_value(account_data, "business_type", "") or "").lower()
    if business_type:
        payout_account.business_type = business_type
    payout_account.is_fully_onboarded = bool(
        charges_enabled and payouts_enabled and not disabled_reason
    )
    _sync_bank_details_from_stripe(payout_account, account_data)
    _sync_owner_profile_from_stripe(payout_account.user, account_data)
    payout_account.last_synced_at = timezone.now()
    payout_account.save()
    return payout_account


def _retrieve_account_with_expand(account_id: str) -> Any:
    """Fetch a Stripe Connect account with needed nested fields expanded."""
    stripe.api_key = _get_stripe_api_key()
    return stripe.Account.retrieve(account_id, expand=CONNECT_ACCOUNT_EXPAND)


def _sanitize_business_url(raw_url: str) -> str:
    """Ensure business profile URL is acceptable to Stripe; fall back to a safe default."""
    cleaned = (raw_url or "").strip()
    if not cleaned:
        return "https://example.com"
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    return cleaned


def ensure_connect_account(user: User, business_type: str | None = None) -> OwnerPayoutAccount:
    """Ensure the owner has a Stripe Connect Express account and sync it locally."""
    stripe.api_key = _get_stripe_api_key()
    job_title = getattr(settings, "CONNECT_JOB_TITLE", "") or "Rentino"
    allowed_business_types = {"individual"}

    def _normalize_business_type(value: str | None) -> str | None:
        if not value:
            return None
        normalized = str(value).strip().lower()
        return normalized if normalized in allowed_business_types else None

    try:
        payout_account = user.payout_account
        existing_account_id = payout_account.stripe_account_id or ""
    except OwnerPayoutAccount.DoesNotExist:
        payout_account = None
        existing_account_id = ""
    desired_business_type = (
        _normalize_business_type(business_type)
        or _normalize_business_type(getattr(payout_account, "business_type", None))
        or "individual"
    )

    business_url = getattr(settings, "CONNECT_BUSINESS_URL", "") or getattr(
        settings, "FRONTEND_ORIGIN", ""
    )
    business_profile = {
        "name": getattr(settings, "CONNECT_BUSINESS_NAME", "") or "Rentino",
        "product_description": getattr(settings, "CONNECT_BUSINESS_PRODUCT_DESCRIPTION", "")
        or "Peer-to-peer rentals platform",
        "url": _sanitize_business_url(business_url),
        "mcc": getattr(settings, "CONNECT_BUSINESS_MCC", "") or "7399",
    }

    account_data: Any | None = None
    if existing_account_id:
        try:
            account_data = _retrieve_account_with_expand(existing_account_id)
        except stripe.error.InvalidRequestError as exc:
            if getattr(exc, "code", "") == "resource_missing":
                logger.info(
                    "Stripe Connect account %s missing for user %s; recreating.",
                    existing_account_id,
                    user.id,
                )
            else:
                _handle_stripe_error(exc)
        except (stripe.error.AuthenticationError, stripe.error.PermissionError) as exc:
            if payout_account is not None:
                logger.warning(
                    "connect_account_sync_skipped",
                    extra={"user_id": user.id, "account_id": existing_account_id},
                )
                payout_account.business_type = desired_business_type
                return payout_account
            _handle_stripe_error(exc)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

        business_url = getattr(settings, "CONNECT_BUSINESS_URL", "") or getattr(
            settings, "FRONTEND_ORIGIN", ""
        )
    individual: dict[str, str] = {}
    if user.first_name:
        individual["first_name"] = user.first_name
    if user.last_name:
        individual["last_name"] = user.last_name
    if user.email:
        individual["email"] = user.email
    if getattr(user, "phone", None):
        individual["phone"] = user.phone
    dob_value = getattr(user, "birth_date", None)
    if dob_value:
        if isinstance(dob_value, str):
            try:
                dob_value = date.fromisoformat(dob_value)
            except ValueError:
                dob_value = None
        elif isinstance(dob_value, datetime):
            dob_value = dob_value.date()
        if dob_value:
            individual["dob"] = {
                "day": dob_value.day,
                "month": dob_value.month,
                "year": dob_value.year,
            }
    address_fields = [
        getattr(user, "street_address", "").strip(),
        getattr(user, "city", "").strip(),
        getattr(user, "province", "").strip(),
        getattr(user, "postal_code", "").strip(),
    ]
    if any(address_fields):
        individual["address"] = {
            "line1": getattr(user, "street_address", ""),
            "city": getattr(user, "city", ""),
            "state": getattr(user, "province", ""),
            "postal_code": getattr(user, "postal_code", ""),
            "country": getattr(user, "country", "CA") or "CA",
        }
    individual["relationship"] = {"title": job_title}

    if account_data is not None:
        actual_type = _normalize_business_type(
            _account_object_value(account_data, "business_type", "")
        )
        if actual_type and actual_type != desired_business_type and existing_account_id:
            try:
                stripe.Account.modify(existing_account_id, business_type=desired_business_type)
                try:
                    account_data = _retrieve_account_with_expand(existing_account_id)
                except stripe.error.StripeError as exc:  # noqa: PERF203
                    _handle_stripe_error(exc)
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

    if account_data is None:
        try:
            account_params = {
                "type": "express",
                "country": "CA",
                "capabilities": {
                    "card_payments": {"requested": True},
                    "transfers": {"requested": True},
                },
                "business_type": desired_business_type,
                "business_profile": business_profile,
                "metadata": {"user_id": str(user.id), "job_title": job_title},
            }
            if individual:
                account_params["individual"] = individual

            account_data = stripe.Account.create(**account_params)
            try:
                account_data = _retrieve_account_with_expand(
                    _account_object_value(account_data, "id", "")
                )
            except stripe.error.StripeError as exc:  # noqa: PERF203
                _handle_stripe_error(exc)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)
    else:
        existing_metadata = _account_object_value(account_data, "metadata", {}) or {}
        if isinstance(existing_metadata, dict):
            metadata_dict = dict(existing_metadata)
        elif hasattr(existing_metadata, "items"):
            metadata_dict = dict(existing_metadata.items())
        else:
            metadata_dict = {}
        desired_metadata = {"user_id": str(user.id), "job_title": job_title}
        metadata_needs_update = any(
            metadata_dict.get(key) != value for key, value in desired_metadata.items()
        )
        if metadata_needs_update and existing_account_id:
            try:
                stripe.Account.modify(
                    existing_account_id,
                    metadata={**metadata_dict, **desired_metadata},
                )
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)
        # Keep individual/relationship in sync when the account already exists.
        if individual and existing_account_id:
            try:
                stripe.Account.modify(existing_account_id, individual=individual)
            except stripe.error.PermissionError:
                logger.warning(
                    "connect_sync_profile_permission_denied",
                    extra={"user_id": user.id, "account_id": existing_account_id},
                )
                # Non-fatal; downstream onboarding flows will surface config issues.
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

    if payout_account is None:
        payout_account = OwnerPayoutAccount(
            user=user,
            stripe_account_id=_account_object_value(account_data, "id", ""),
            business_type=desired_business_type,
        )
    else:
        payout_account.business_type = desired_business_type

    return _sync_payout_account_from_stripe(payout_account, account_data)


def get_connect_available_balance(payout_account: OwnerPayoutAccount) -> Decimal | None:
    """Return the available balance (in dollars) for a Stripe Connect account, if known."""
    account_id = getattr(payout_account, "stripe_account_id", "") or ""
    if not account_id:
        return None

    stripe.api_key = _get_stripe_api_key()
    try:
        balance = stripe.Balance.retrieve(stripe_account=account_id)
    except stripe.error.StripeError as exc:
        logger.warning(
            "stripe_balance_unavailable",
            extra={"account_id": account_id, "error": str(exc)},
        )
        return None

    available_list = getattr(balance, "available", None) or []
    available_cents = None
    for entry in available_list:
        currency = ""
        amount = None
        try:
            currency = (entry.get("currency") or "").lower()
            amount = entry.get("amount")
        except AttributeError:
            currency = getattr(entry, "currency", "") or ""
            amount = getattr(entry, "amount", None)
            currency = currency.lower()

        if currency == "cad":
            available_cents = amount
            break

    if available_cents is None:
        return None

    try:
        return (Decimal(str(available_cents)) / Decimal("100")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def sync_connect_account_personal_info(
    user: User,
    *,
    business_type: str | None = None,
    payout_account: OwnerPayoutAccount | None = None,
    # kept for backwards compatibility; permission errors are now non-fatal
    fail_on_permission: bool = False,
) -> None:
    """Push the user's personal details to Stripe Connect."""
    payout_account = payout_account or ensure_connect_account(user, business_type=business_type)
    stripe.api_key = _get_stripe_api_key()
    individual: dict[str, Any] = {}

    if user.first_name:
        individual["first_name"] = user.first_name
    if user.last_name:
        individual["last_name"] = user.last_name
    if user.email:
        individual["email"] = user.email
    phone_value = getattr(user, "phone", None)
    if phone_value is None and getattr(user, "pk", None):
        try:
            phone_value = User.objects.filter(pk=user.pk).values_list("phone", flat=True).first()
        except Exception:
            phone_value = None
    individual["phone"] = phone_value or ""
    if getattr(user, "birth_date", None):
        dob_value = user.birth_date
        if isinstance(dob_value, str):
            try:
                dob_value = date.fromisoformat(dob_value)
            except ValueError:
                dob_value = None
        elif isinstance(dob_value, datetime):
            dob_value = dob_value.date()
        if dob_value:
            individual["dob"] = {
                "day": dob_value.day,
                "month": dob_value.month,
                "year": dob_value.year,
            }

    address_fields = [
        getattr(user, "street_address", "").strip(),
        getattr(user, "city", "").strip(),
        getattr(user, "province", "").strip(),
        getattr(user, "postal_code", "").strip(),
    ]
    if any(address_fields):
        individual["address"] = {
            "line1": getattr(user, "street_address", ""),
            "city": getattr(user, "city", ""),
            "state": getattr(user, "province", ""),
            "postal_code": getattr(user, "postal_code", ""),
            "country": getattr(user, "country", "CA") or "CA",
        }

    if not individual:
        return

    def _log_prefill_failure(exc: Exception, *, level: int = logging.WARNING) -> None:
        logger.log(
            level,
            "connect_prefill_failed",
            extra={
                "user_id": user.id,
                "account_id": payout_account.stripe_account_id,
                "error": str(exc),
                "stripe_error_code": getattr(exc, "code", None),
                "stripe_error_type": getattr(getattr(exc, "error", None), "type", None)
                or exc.__class__.__name__,
                "stripe_request_id": getattr(exc, "request_id", None),
            },
        )

    try:
        stripe.Account.modify(
            payout_account.stripe_account_id,
            individual=individual,
        )
    except TypeError as exc:
        # Defensive: some older stripe-mock exceptions may raise TypeError on bad kwargs.
        _log_prefill_failure(exc)
        return
    except stripe.error.PermissionError as exc:
        _log_prefill_failure(exc)
        return
    except stripe.error.StripeError as exc:
        _log_prefill_failure(exc, level=logging.ERROR)
        _handle_stripe_error(exc)


def update_connect_bank_account(
    *,
    payout_account: OwnerPayoutAccount,
    transit_number: str,
    institution_number: str,
    account_number: str,
) -> dict[str, Any]:
    """
    Attach or update the default external bank account for this Stripe Connect account.
    Returns the Stripe bank account object.
    """
    stripe.api_key = _get_stripe_api_key()

    routing_number = f"{institution_number}{transit_number}"

    try:
        bank_account = stripe.Account.create_external_account(
            payout_account.stripe_account_id,
            external_account={
                "object": "bank_account",
                "country": "CA",
                "currency": "cad",
                "account_number": account_number,
                "routing_number": routing_number,
            },
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)
    return bank_account


def _get_frontend_origin() -> str:
    """Return the configured frontend origin or a local fallback."""
    configured = (getattr(settings, "FRONTEND_ORIGIN", "") or "").strip()
    base = configured or "http://localhost:5173"
    return base.rstrip("/") or base


def _promotion_checkout_urls(listing_id: int) -> tuple[str, str]:
    """Return the success and cancel URLs for promotion checkout sessions."""
    base_origin = _get_frontend_origin()
    base_path = f"{base_origin}/owner/listings/{listing_id}/promotions"
    success_url = f"{base_path}?status=success&session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{base_path}?status=cancel"
    return success_url, cancel_url


def _get_platform_account_id() -> str:
    """Return the platform's Stripe account id, inferring from API key if unset."""
    configured = (getattr(settings, "STRIPE_PLATFORM_ACCOUNT_ID", "") or "").strip()
    if configured:
        return configured

    stripe.api_key = _get_stripe_api_key()
    try:
        acct = stripe.Account.retrieve()
    except stripe.error.StripeError as exc:
        raise StripeConfigurationError(
            "Stripe platform account id is not configured; set STRIPE_PLATFORM_ACCOUNT_ID."
        ) from exc

    acct_id = getattr(acct, "id", None)
    if acct_id is None and hasattr(acct, "get"):
        acct_id = acct.get("id")
    acct_id = (acct_id or "").strip()
    if not acct_id:
        raise StripeConfigurationError(
            "Stripe platform account id is not configured; set STRIPE_PLATFORM_ACCOUNT_ID."
        )
    return acct_id


def transfer_earnings_to_platform(
    *,
    payout_account: OwnerPayoutAccount,
    amount_cents: int,
    metadata: dict[str, str] | None = None,
) -> str:
    """
    Move funds from an owner's Stripe Connect balance to the platform account.

    Returns the Stripe transfer id.
    """
    platform_account = _get_platform_account_id()

    stripe.api_key = _get_stripe_api_key()
    base_metadata = {
        "kind": "promotion_earnings_payment",
        "stripe_account_id": payout_account.stripe_account_id,
        "env": getattr(settings, "STRIPE_ENV", "dev") or "dev",
    }
    if metadata:
        base_metadata.update(metadata)

    try:
        transfer = stripe.Transfer.create(
            amount=amount_cents,
            currency="cad",
            destination=platform_account,
            description="Promotion payment from owner earnings",
            metadata=base_metadata,
            stripe_account=payout_account.stripe_account_id,
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    transfer_id = getattr(transfer, "id", None)
    if transfer_id is None and hasattr(transfer, "get"):
        transfer_id = transfer.get("id")
    return transfer_id or ""


def create_promotion_checkout_session(
    *,
    owner: User,
    listing: Listing,
    amount_cents: int,
    duration_days: int,
    starts_at: datetime,
    ends_at: datetime,
    cache_scope: object | None = None,
) -> tuple[str, str]:
    """Create a Stripe Checkout session used to buy a promoted listing slot."""
    stripe.api_key = _get_stripe_api_key()
    customer_id = ensure_stripe_customer(owner, cache_scope=cache_scope)

    success_url, cancel_url = _promotion_checkout_urls(listing.id)
    if amount_cents <= 0:
        raise StripePaymentError("Promotion total price must be greater than zero.")

    existing_session = (
        PromotionCheckoutSession.objects.filter(
            owner=owner,
            listing=listing,
            starts_at=starts_at,
            ends_at=ends_at,
            amount_cents=amount_cents,
            consumed_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    now = timezone.now()
    if existing_session:
        age = now - (existing_session.updated_at or existing_session.created_at)
        if existing_session.status == "open" and age < CHECKOUT_SESSION_REFRESH_AGE:
            return existing_session.stripe_session_id, existing_session.session_url

        if existing_session.status == "open":
            try:
                _log_stripe_call(
                    "checkout_session.retrieve",
                    listing_id=listing.id,
                    owner_id=owner.id,
                )
                refreshed = stripe.checkout.Session.retrieve(existing_session.stripe_session_id)
                session_status = getattr(refreshed, "status", "") or existing_session.status
                session_url = getattr(refreshed, "url", None) or existing_session.session_url
                if session_status == "open":
                    updates = []
                    if session_url and session_url != existing_session.session_url:
                        existing_session.session_url = session_url
                        updates.append("session_url")
                    if session_status != existing_session.status:
                        existing_session.status = session_status
                        updates.append("status")
                    if updates:
                        existing_session.save(update_fields=updates)
                    return existing_session.stripe_session_id, session_url

                existing_session.status = session_status or existing_session.status
                existing_session.consumed_at = existing_session.consumed_at or now
                existing_session.save(update_fields=["status", "consumed_at"])
            except stripe.error.InvalidRequestError:
                existing_session.status = "expired"
                existing_session.consumed_at = existing_session.consumed_at or now
                existing_session.save(update_fields=["status", "consumed_at"])
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

    listing_title = (listing.title or "").strip()
    product_name = f"Listing promotion ({duration_days} days)"
    date_range_text = f"{starts_at.date().isoformat()} to {ends_at.date().isoformat()}"
    description = (
        f"{duration_days}-day promotion for listing {listing_title} ({date_range_text})"
        if listing_title
        else f"{duration_days}-day listing promotion ({date_range_text})"
    )
    metadata = {
        "env": getattr(settings, "STRIPE_ENV", "dev") or "dev",
        "kind": "promotion_slot",
        "listing_id": str(listing.id),
        "owner_id": str(owner.id),
        "starts_at": starts_at.isoformat(),
        "ends_at": ends_at.isoformat(),
        "duration_days": str(duration_days),
    }

    try:
        _log_stripe_call(
            "checkout_session.create",
            listing_id=listing.id,
            owner_id=owner.id,
            amount_cents=amount_cents,
        )
        session = stripe.checkout.Session.create(
            mode="payment",
            customer=customer_id,
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=f"listing:{listing.id}:promotion",
            metadata=metadata,
            line_items=[
                {
                    "price_data": {
                        "currency": "cad",
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": product_name,
                            "description": description,
                        },
                    },
                    "quantity": 1,
                }
            ],
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    session_id = getattr(session, "id", None)
    if not session_id and hasattr(session, "get"):
        session_id = session.get("id")
    session_url = getattr(session, "url", None)
    if not session_url and hasattr(session, "get"):
        session_url = session.get("url")
    if not session_id or not session_url:
        raise StripeConfigurationError("Stripe did not return a checkout session URL.")

    session_status = getattr(session, "status", "") or "open"
    PromotionCheckoutSession.objects.create(
        owner=owner,
        listing=listing,
        starts_at=starts_at,
        ends_at=ends_at,
        amount_cents=amount_cents,
        stripe_session_id=session_id,
        session_url=session_url,
        status=session_status,
    )

    return session_id, session_url


def create_connect_onboarding_link(
    user: User,
    payout_account: OwnerPayoutAccount | None = None,
    business_type: str | None = None,
) -> str:
    """Create a Stripe Connect onboarding link for the owner."""
    payout_account = payout_account or ensure_connect_account(user, business_type=business_type)
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
            collect="eventually_due",
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    link_url = getattr(link, "url", None) or link.get("url")  # type: ignore[arg-type]
    if not link_url:
        raise StripeConfigurationError("Stripe did not return an onboarding link.")
    return link_url


def create_connect_onboarding_session(
    user: User,
    business_type: str | None = None,
) -> dict[str, Any]:
    """
    Create an embedded Connect Account Session for onboarding.

    Returns a payload containing client_secret, stripe_account_id, expires_at (ISO string),
    a legacy onboarding_url fallback (may be None), and the mode ("embedded" or "hosted_fallback").
    """
    payout_account = ensure_connect_account(user, business_type=business_type)
    # Best-effort: prefill safe personal info so embedded onboarding is hydrated.
    try:
        sync_connect_account_personal_info(
            user,
            business_type=business_type,
            payout_account=payout_account,
            fail_on_permission=False,
        )
    except Exception as exc:  # pragma: no cover - defensive catch; logging happens in sync helper
        logger.warning(
            "connect_prefill_failed",
            extra={
                "user_id": user.id,
                "account_id": payout_account.stripe_account_id,
                "error": str(exc),
            },
        )
        raise

    stripe.api_key = _get_stripe_api_key()

    def _log_stripe_issue(event_name: str, exc: Exception, *, level: int = logging.WARNING) -> None:
        logger.log(
            level,
            event_name,
            extra={
                "user_id": user.id,
                "account_id": payout_account.stripe_account_id,
                "error": str(exc),
                "stripe_error_code": getattr(exc, "code", None),
                "stripe_error_type": getattr(getattr(exc, "error", None), "type", None)
                or exc.__class__.__name__,
                "stripe_request_id": getattr(exc, "request_id", None),
            },
        )

    def _serialize_expires(raw_value: Any) -> str | None:
        if raw_value in (None, ""):
            return None
        try:
            parsed = int(raw_value)
        except (TypeError, ValueError):
            return str(raw_value)
        return (
            datetime.fromtimestamp(parsed, tz=datetime_timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    session = None
    try:
        session = stripe.AccountSession.create(
            account=payout_account.stripe_account_id,
            components={"account_onboarding": {"enabled": True}},
        )
    except (stripe.error.StripeError, TypeError) as exc:
        _log_stripe_issue("connect_account_session_failed", exc)
        session = None

    def _safe_create_onboarding_link(raise_on_error: bool) -> str | None:
        try:
            return create_connect_onboarding_link(
                user,
                payout_account=payout_account,
                business_type=business_type,
            )
        except (
            Exception
        ) as exc:  # noqa: BLE001 - we want to capture custom Stripe exception classes too
            _log_stripe_issue(
                "connect_account_link_failed",
                exc,
                level=logging.ERROR if raise_on_error else logging.WARNING,
            )
            if raise_on_error:
                raise
            return None

    if session is None:
        onboarding_url = _safe_create_onboarding_link(raise_on_error=True)
        return {
            "client_secret": None,
            "stripe_account_id": payout_account.stripe_account_id,
            "expires_at": None,
            "onboarding_url": onboarding_url,
            "mode": "hosted_fallback",
        }

    onboarding_url = _safe_create_onboarding_link(raise_on_error=False)

    client_secret = getattr(session, "client_secret", None)
    if client_secret is None and hasattr(session, "get"):
        client_secret = session.get("client_secret")

    expires_at = getattr(session, "expires_at", None)
    if expires_at is None and hasattr(session, "get"):
        expires_at = session.get("expires_at")

    mode = "embedded" if client_secret else "hosted_fallback"

    return {
        "client_secret": client_secret,
        "stripe_account_id": payout_account.stripe_account_id,
        "expires_at": _serialize_expires(expires_at),
        "onboarding_url": onboarding_url,
        "mode": mode,
    }


def create_instant_payout(
    *,
    user: User,
    payout_account: OwnerPayoutAccount,
    amount_cents: int,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """
    Create an instant payout from the owner's Stripe Connect account balance
    to their default external bank account.

    amount_cents: integer amount in cents AFTER fee (the amount going to owner).
    """
    if amount_cents <= 0:
        raise StripeConfigurationError("Instant payout amount must be positive.")

    if not payout_account.stripe_account_id:
        raise StripeConfigurationError("Owner is missing a Stripe Connect account id.")

    stripe.api_key = _get_stripe_api_key()

    base_metadata = {
        "kind": "instant_payout",
        "user_id": str(user.id),
        "stripe_account_id": payout_account.stripe_account_id,
        "env": getattr(settings, "STRIPE_ENV", "dev") or "dev",
    }
    if metadata:
        base_metadata.update(metadata)

    try:
        payout = stripe.Payout.create(
            amount=amount_cents,
            currency="cad",
            metadata=base_metadata,
            stripe_account=payout_account.stripe_account_id,
            # You can add a statement_descriptor if desired.
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    return payout


def create_owner_transfer_for_booking(*, booking: Booking, payment_intent_id: str) -> None:
    """Transfer the owner's share of a paid booking to their Connect account."""
    if getattr(settings, "STRIPE_BOOKINGS_DESTINATION_CHARGES", True):
        logger.debug(
            "Skipping owner transfer; destination charges enabled.",
            extra={"booking_id": booking.id},
        )
        return

    if not booking.totals:
        return

    listing = getattr(booking, "listing", None)
    owner = getattr(listing, "owner", None)
    if owner is None:
        return

    fees = _extract_booking_fees(booking)
    owner_payout = fees["owner_payout"]
    platform_fee_total = fees["platform_fee_total"]

    if owner_payout <= Decimal("0"):
        return

    existing_owner_txn = Transaction.objects.filter(
        user=owner,
        booking=booking,
        kind=Transaction.Kind.OWNER_EARNING,
    ).exists()
    if existing_owner_txn:
        return

    payout_account = ensure_connect_account(owner)
    if not payout_account.stripe_account_id or not payout_account.payouts_enabled:
        logger.warning(
            "Owner payout skipped; missing Stripe account or payouts disabled.",
            extra={
                "booking_id": booking.id,
                "owner_id": owner.id,
                "stripe_account_id": payout_account.stripe_account_id,
            },
        )
        return

    stripe.api_key = _get_stripe_api_key()
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"
    amount_cents = _to_cents(owner_payout)

    try:
        transfer = stripe.Transfer.create(
            amount=amount_cents,
            currency="cad",
            destination=payout_account.stripe_account_id,
            description=f"Owner payout for booking #{booking.id}",
            metadata={
                "kind": "owner_payout",
                "booking_id": str(booking.id),
                "listing_id": str(booking.listing_id),
                "env": env_label,
                "charge_payment_intent_id": payment_intent_id,
                "platform_fee_total": str(platform_fee_total),
            },
            transfer_group=f"booking:{booking.id}:owner_payout_v1",
            idempotency_key=f"booking:{booking.id}:owner_payout_v1",
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    transfer_id = getattr(transfer, "id", None)
    if transfer_id is None and hasattr(transfer, "get"):
        transfer_id = transfer.get("id")

    log_transaction(
        user=owner,
        booking=booking,
        promotion_slot=None,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=owner_payout,
        currency="cad",
        stripe_id=transfer_id,
    )


def _handle_connect_account_updated_event(account_payload: Any) -> None:
    """Sync OwnerPayoutAccount rows based on Stripe account.updated data."""
    stripe_account_id = _account_object_value(account_payload, "id", "")
    if not stripe_account_id:
        return

    needs_expand = not _account_object_value(
        account_payload, "individual", None
    ) or not _account_object_value(  # noqa: E501
        account_payload, "external_accounts", None
    )
    if needs_expand:
        try:
            account_payload = _retrieve_account_with_expand(stripe_account_id)
        except Exception:  # Defensive: best-effort sync without failing webhook
            pass

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

    payout_account = _sync_payout_account_from_stripe(payout_account, account_payload)

    if payout_account.is_fully_onboarded:
        try:
            IdentityVerification.objects.update_or_create(
                user=payout_account.user,
                session_id=stripe_account_id,
                defaults={
                    "status": IdentityVerification.Status.VERIFIED,
                    "verified_at": timezone.now(),
                    "last_error_code": "",
                    "last_error_reason": "",
                },
            )
        except Exception:
            logger.warning(
                "connect_identity_mark_failed",
                extra={"user_id": payout_account.user_id, "account_id": stripe_account_id},
                exc_info=True,
            )


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


def _extract_transfer_id_from_intent(intent_payload: Any) -> str | None:
    """Best-effort extraction of a transfer id from a PaymentIntent payload."""
    if not intent_payload:
        return None
    if isinstance(intent_payload, dict):
        charges = intent_payload.get("charges")
    else:
        charges = getattr(intent_payload, "charges", None)
    if charges is None:
        return None
    if isinstance(charges, dict):
        charge_data = charges.get("data") or []
    else:
        charge_data = getattr(charges, "data", []) or []
    if not charge_data:
        return None
    charge = charge_data[0]
    if isinstance(charge, dict):
        transfer = charge.get("transfer")
    else:
        transfer = getattr(charge, "transfer", None)
    if isinstance(transfer, dict):
        transfer_id = transfer.get("id")
    else:
        transfer_id = getattr(transfer, "id", None)
    if transfer_id:
        return str(transfer_id)
    if isinstance(transfer, str):
        return transfer
    return None


def _extract_application_fee_from_intent(intent_payload: Any) -> tuple[str | None, str | None]:
    """Best-effort extraction of an application fee id/description from a PaymentIntent."""
    if not intent_payload:
        return None, None
    if isinstance(intent_payload, dict):
        charges = intent_payload.get("charges")
    else:
        charges = getattr(intent_payload, "charges", None)
    if charges is None:
        return None, None
    if isinstance(charges, dict):
        charge_data = charges.get("data") or []
    else:
        charge_data = getattr(charges, "data", []) or []
    if not charge_data:
        return None, None
    charge = charge_data[0]
    if isinstance(charge, dict):
        application_fee = charge.get("application_fee")
    else:
        application_fee = getattr(charge, "application_fee", None)
    fee_id = None
    description = None
    if isinstance(application_fee, dict):
        fee_id = application_fee.get("id")
        description = application_fee.get("description")
    else:
        fee_id = getattr(application_fee, "id", None)
        description = getattr(application_fee, "description", None)
    if fee_id:
        return str(fee_id), description
    if isinstance(application_fee, str):
        return application_fee, description
    return None, description


def _extract_latest_charge_id(intent_payload: Any) -> str | None:
    """Best-effort extraction of a latest_charge id from a PaymentIntent payload."""
    if not intent_payload:
        return None
    if isinstance(intent_payload, dict):
        latest_charge = intent_payload.get("latest_charge")
    else:
        latest_charge = getattr(intent_payload, "latest_charge", None)
    if latest_charge:
        return str(latest_charge)
    return None


def _maybe_update_application_fee_description(
    *,
    booking_id: int,
    intent_payload: Any,
    intent_id: str | None = None,
) -> None:
    """Ensure the application fee description includes the booking id."""
    fee_id, fee_description = _extract_application_fee_from_intent(intent_payload)
    if not fee_id and intent_id:
        intent_payload = _retrieve_intent_with_transfer(intent_id)
        fee_id, fee_description = _extract_application_fee_from_intent(intent_payload)
    if not fee_id:
        latest_charge_id = _extract_latest_charge_id(intent_payload)
        if latest_charge_id:
            try:
                stripe.api_key = _get_stripe_api_key()
                charge = stripe.Charge.retrieve(latest_charge_id)
            except StripeConfigurationError:
                return
            except stripe.error.StripeError:
                logger.warning(
                    "stripe_webhook: failed to retrieve charge %s for fee description",
                    latest_charge_id,
                    exc_info=True,
                )
                return
            if isinstance(charge, dict):
                application_fee = charge.get("application_fee")
            else:
                application_fee = getattr(charge, "application_fee", None)
            if isinstance(application_fee, dict):
                fee_id = application_fee.get("id")
                fee_description = application_fee.get("description")
            else:
                fee_id = getattr(application_fee, "id", None)
                fee_description = getattr(application_fee, "description", None)
            if not fee_id and isinstance(application_fee, str):
                fee_id = application_fee

    if not fee_id:
        return

    desired_description = f"Application fee for booking #{booking_id}"
    if (fee_description or "").strip() == desired_description:
        return

    try:
        stripe.api_key = _get_stripe_api_key()
    except StripeConfigurationError:
        return
    try:
        stripe.ApplicationFee.modify(fee_id, description=desired_description)
    except stripe.error.StripeError:
        logger.warning(
            "stripe_webhook: failed to update application fee %s description",
            fee_id,
            exc_info=True,
        )


def _retrieve_intent_with_transfer(intent_id: str) -> Any | None:
    """Retrieve a PaymentIntent with expanded transfer details, if possible."""
    if not intent_id:
        return None
    try:
        stripe.api_key = _get_stripe_api_key()
    except StripeConfigurationError:
        return None
    try:
        return stripe.PaymentIntent.retrieve(
            intent_id,
            expand=["charges.data.transfer", "charges.data.application_fee"],
        )
    except TypeError:
        try:
            return stripe.PaymentIntent.retrieve(intent_id)
        except Exception:  # noqa: BLE001 - tolerate stubbed SDKs
            return None
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") == "resource_missing":
            return None
        logger.warning(
            "stripe_webhook: failed to retrieve PaymentIntent %s",
            intent_id,
            exc_info=True,
        )
    except stripe.error.StripeError:
        logger.warning(
            "stripe_webhook: failed to retrieve PaymentIntent %s",
            intent_id,
            exc_info=True,
        )
    return None


def create_booking_charge_intent(
    *,
    booking: Booking,
    customer_id: str,
    payment_method_id: str,
    attached_via_setup_intent: bool = False,
    cache_scope: object | None = None,
) -> str:
    """
    Create or reuse the rental charge PaymentIntent (automatic capture).
    """
    fees = _extract_booking_fees(booking)
    rental_subtotal = fees["rental_subtotal"]
    renter_fee = fees["renter_fee"]
    owner_fee = fees["owner_fee"]
    platform_fee_total = fees["platform_fee_total"]
    owner_payout = fees["owner_payout"]

    charge_amount = rental_subtotal + renter_fee
    if charge_amount <= Decimal("0"):
        raise StripePaymentError("Rental charge must be greater than zero.")
    charge_amount_cents = _to_cents(charge_amount)
    platform_fee_cents = _to_cents(platform_fee_total)
    owner_payout_cents = _to_cents(owner_payout)

    listing = getattr(booking, "listing", None)
    if listing is None:
        listing = Listing.objects.select_related("owner").filter(pk=booking.listing_id).first()
    owner = getattr(listing, "owner", None) or getattr(booking, "owner", None)
    if owner is None:
        raise StripePaymentError("Listing owner is missing; please contact support.")

    payout_account = ensure_connect_account(owner)
    if not payout_account.stripe_account_id or not payout_account.charges_enabled:
        raise StripePaymentError(
            "Listing owner is not ready to accept payments yet. Please try again later."
        )

    if owner_payout_cents > charge_amount_cents:
        raise StripePaymentError("Booking payout exceeds the total charge amount.")

    stripe.api_key = _get_stripe_api_key()
    customer_value = (
        customer_id or getattr(booking.renter, "stripe_customer_id", "") or ""
    ).strip() or None
    if customer_value and payment_method_id:
        _ensure_payment_method_for_customer(
            payment_method_id,
            customer_value,
            attached_via_setup_intent=attached_via_setup_intent,
            cache_scope=cache_scope,
        )

    idempotency_base = f"booking:{booking.id}:{IDEMPOTENCY_VERSION}"
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"
    totals = booking.totals or {}
    common_metadata = {
        "booking_id": str(booking.id),
        "listing_id": str(booking.listing_id),
        "owner_id": str(owner.id),
        "owner_stripe_account_id": payout_account.stripe_account_id,
        "rental_subtotal": str(rental_subtotal),
        "renter_fee": str(renter_fee),
        "owner_fee": str(owner_fee),
        "platform_fee_total": str(platform_fee_total),
        "owner_payout": str(owner_payout),
        "renter_fee_base": str(totals.get("renter_fee_base", totals.get("renter_fee", ""))),
        "renter_fee_gst": str(totals.get("renter_fee_gst", "")),
        "renter_fee_total": str(totals.get("renter_fee_total", "")),
        "owner_fee_base": str(totals.get("owner_fee_base", totals.get("owner_fee", ""))),
        "owner_fee_gst": str(totals.get("owner_fee_gst", "")),
        "owner_fee_total": str(totals.get("owner_fee_total", "")),
        "gst_enabled": str(totals.get("gst_enabled", False)),
        "gst_rate": str(totals.get("gst_rate", "")),
        "gst_number": str(totals.get("gst_number", "")),
        "env": env_label,
    }
    currency = "cad"
    use_destination_charges = getattr(settings, "STRIPE_BOOKINGS_DESTINATION_CHARGES", True)

    charge_intent = _retrieve_payment_intent(
        getattr(booking, "charge_payment_intent_id", ""),
        label="booking_charge",
    )
    if charge_intent is not None:
        status = (getattr(charge_intent, "status", "") or "").lower()
        intent_amount = getattr(charge_intent, "amount", None)
        needs_recreate = False
        already_canceled = status == "canceled"
        if status == "succeeded":
            needs_recreate = False
        elif intent_amount not in (None, charge_amount_cents):
            needs_recreate = True
        elif use_destination_charges:
            intent_fee = getattr(charge_intent, "application_fee_amount", None)
            transfer_data = getattr(charge_intent, "transfer_data", None)
            if isinstance(transfer_data, dict):
                transfer_destination = transfer_data.get("destination")
            else:
                transfer_destination = getattr(transfer_data, "destination", None)
            if (
                intent_fee != platform_fee_cents
                or transfer_destination != payout_account.stripe_account_id
            ):
                needs_recreate = True
        elif already_canceled:
            needs_recreate = True

        if needs_recreate and not already_canceled:
            try:
                stripe.PaymentIntent.cancel(charge_intent.id)
            except stripe.error.InvalidRequestError as exc:
                if getattr(exc, "code", "") != "resource_missing":
                    _handle_stripe_error(exc)
            except stripe.error.StripeError as exc:  # noqa: PERF203
                _handle_stripe_error(exc)
            charge_intent = None
        elif already_canceled:
            charge_intent = None

    if charge_intent is None:
        try:
            charge_payload: dict[str, Any] = {
                "amount": charge_amount_cents,
                "currency": currency,
                "automatic_payment_methods": {**AUTOMATIC_PAYMENT_METHODS_CONFIG},
                "customer": customer_value,
                "payment_method": payment_method_id or None,
                "confirm": bool(payment_method_id),
                "off_session": False,
                "capture_method": "automatic",
                "metadata": {**common_metadata, "kind": "booking_charge"},
                "idempotency_key": f"{idempotency_base}:charge:{charge_amount_cents}",
            }
            if use_destination_charges:
                transfer_data: dict[str, Any] = {
                    "destination": payout_account.stripe_account_id,
                    "amount": owner_payout_cents,
                }
                charge_payload.update(
                    {
                        "application_fee_amount": platform_fee_cents,
                        "transfer_data": transfer_data,
                        "transfer_group": f"booking:{booking.id}",
                        "on_behalf_of": payout_account.stripe_account_id,
                        "idempotency_key": (
                            f"{idempotency_base}:charge_dest_v1:"
                            f"{charge_amount_cents}:{platform_fee_cents}:"
                            f"{payout_account.stripe_account_id}"
                        ),
                    }
                )

            charge_intent = stripe.PaymentIntent.create(**charge_payload)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    charge_intent_id = charge_intent.id
    booking.charge_payment_intent_id = charge_intent_id
    booking.save(update_fields=["charge_payment_intent_id"])

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

    return charge_intent_id


def create_booking_deposit_hold_intent(
    *,
    booking: Booking,
    customer_id: str,
    payment_method_id: str,
    attached_via_setup_intent: bool = False,
    cache_scope: object | None = None,
) -> str | None:
    """
    Create or reuse the damage deposit PaymentIntent (manual capture).
    """
    totals = booking.totals or {}
    damage_deposit = _parse_decimal(totals.get("damage_deposit", "0"), "damage_deposit")
    if damage_deposit < Decimal("0"):
        raise StripePaymentError("Damage deposit cannot be negative.")
    if damage_deposit <= Decimal("0"):
        return None
    deposit_amount_cents = _to_cents(damage_deposit)

    stripe.api_key = _get_stripe_api_key()
    customer_value = (
        customer_id or getattr(booking.renter, "stripe_customer_id", "") or ""
    ).strip()
    if not customer_value:
        raise StripePaymentError("Stripe customer id is required to authorize a deposit.")
    if not payment_method_id:
        raise StripePaymentError("Payment method id is required to authorize a deposit.")

    _ensure_payment_method_for_customer(
        payment_method_id,
        customer_value,
        attached_via_setup_intent=attached_via_setup_intent,
        cache_scope=cache_scope,
    )

    idempotency_base = f"booking:{booking.id}:{IDEMPOTENCY_VERSION}"
    env_label = getattr(settings, "STRIPE_ENV", "dev") or "dev"
    common_metadata = {
        "booking_id": str(booking.id),
        "listing_id": str(booking.listing_id),
        "env": env_label,
    }
    currency = "cad"

    deposit_field_name = None
    if hasattr(booking, "deposit_payment_intent_id"):
        deposit_field_name = "deposit_payment_intent_id"
    elif hasattr(booking, "deposit_hold_id"):
        deposit_field_name = "deposit_hold_id"

    existing_id = ""
    if deposit_field_name:
        existing_id = getattr(booking, deposit_field_name, "") or ""

    deposit_intent = _retrieve_payment_intent(existing_id, label="damage_deposit")
    if deposit_intent is not None:
        status = (getattr(deposit_intent, "status", "") or "").lower()
        intent_amount = getattr(deposit_intent, "amount", None)
        if status == "succeeded":
            return deposit_intent.id
        if intent_amount not in (None, deposit_amount_cents):
            _cancel_payment_intent(deposit_intent.id)
            deposit_intent = None
        elif status in {"requires_capture", "processing"}:
            pass
        else:
            if _cancel_payment_intent(deposit_intent.id):
                deposit_intent = None

    if deposit_intent is None:
        try:
            deposit_intent = stripe.PaymentIntent.create(
                amount=deposit_amount_cents,
                currency=currency,
                automatic_payment_methods={**AUTOMATIC_PAYMENT_METHODS_CONFIG},
                customer=customer_value,
                payment_method=payment_method_id,
                confirm=True,
                off_session=True,
                capture_method="manual",
                metadata={**common_metadata, "kind": "damage_deposit"},
                idempotency_key=f"{idempotency_base}:deposit:{deposit_amount_cents}",
            )
        except stripe.error.CardError as exc:
            decline_code = getattr(exc, "decline_code", "") or ""
            if decline_code == "insufficient_funds":
                raise DepositAuthorizationInsufficientFunds(
                    exc.user_message or "Insufficient funds for damage deposit."
                ) from exc
            _handle_stripe_error(exc)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    deposit_intent_id = deposit_intent.id
    update_fields = []
    if deposit_field_name:
        setattr(booking, deposit_field_name, deposit_intent_id or "")
        update_fields.append(deposit_field_name)
    if update_fields:
        booking.save(update_fields=update_fields)

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

    return deposit_intent_id


def create_booking_payment_intents(
    *,
    booking: Booking,
    customer_id: str,
    payment_method_id: str,
) -> tuple[str, str | None]:
    """
    Backwards-compatible wrapper that now only creates the rental charge intent.

    Deposit holds are authorized separately on the booking start day.
    """
    charge_id = create_booking_charge_intent(
        booking=booking,
        customer_id=customer_id,
        payment_method_id=payment_method_id,
    )
    return charge_id, None


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
        raise StripeConfigurationError("Rentino is missing a Stripe customer id.")

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


def release_deposit_hold(booking: Booking) -> None:
    """Release a damage deposit hold for a completed booking."""
    deposit_intent_id = (getattr(booking, "deposit_hold_id", "") or "").strip()
    if not deposit_intent_id:
        return

    totals = booking.totals or {}
    damage_deposit = _parse_decimal(totals.get("damage_deposit"), "damage_deposit")
    if damage_deposit <= Decimal("0"):
        return

    existing_release = Transaction.objects.filter(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        stripe_id=deposit_intent_id,
    ).first()
    if existing_release is not None:
        return

    stripe.api_key = _get_stripe_api_key()
    intent = None
    try:
        intent = stripe.PaymentIntent.retrieve(deposit_intent_id)
        retrieved_id = getattr(intent, "id", "") or deposit_intent_id
        deposit_intent_id = retrieved_id
    except stripe.error.InvalidRequestError as exc:
        if getattr(exc, "code", "") == "resource_missing":
            logger.info(
                "Stripe deposit PaymentIntent %s missing for booking %s; treating as released.",
                deposit_intent_id,
                booking.id,
            )
        else:
            _handle_stripe_error(exc)
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    if intent is not None:
        status = getattr(intent, "status", "") or ""
        if status == "succeeded":
            return
        if status != "canceled" and status in (
            "requires_capture",
            "requires_payment_method",
            "requires_confirmation",
            "requires_action",
            "processing",
        ):
            try:
                canceled_intent = stripe.PaymentIntent.cancel(deposit_intent_id)
                canceled_id = getattr(canceled_intent, "id", "") or deposit_intent_id
                deposit_intent_id = canceled_id
            except stripe.error.InvalidRequestError as exc:
                if getattr(exc, "code", "") == "resource_missing":
                    logger.info(
                        "Stripe deposit PaymentIntent %s already released for booking %s.",
                        deposit_intent_id,
                        booking.id,
                    )
                else:
                    _handle_stripe_error(exc)
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

    log_transaction(
        user=booking.renter,
        booking=booking,
        kind=Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        amount=damage_deposit,
        currency="cad",
        stripe_id=deposit_intent_id,
    )


def _get_customer_cache(cache_scope: object | None) -> dict[int, str]:
    """
    Return a per-request (or per-context) cache for Stripe customers.

    When cache_scope is provided (e.g., the DRF request object), store the cache on it to
    avoid leaking state across requests. Otherwise fall back to a contextvar-scoped cache.
    """
    if cache_scope is not None:
        cached = getattr(cache_scope, "_stripe_customer_cache", None)
        if cached is None:
            cached = {}
            cache_scope._stripe_customer_cache = cached  # type: ignore[attr-defined]
        return cached

    cached = _CUSTOMER_CACHE.get(None)
    if cached is None:
        cached = {}
        _CUSTOMER_CACHE.set(cached)
    return cached


def _get_payment_method_cache(cache_scope: object | None) -> dict[str, Any]:
    """
    Return a request/context-scoped cache for Stripe PaymentMethod lookups.
    """
    if cache_scope is not None:
        cached = getattr(cache_scope, "_stripe_payment_method_cache", None)
        if cached is None:
            cached = {}
            cache_scope._stripe_payment_method_cache = cached  # type: ignore[attr-defined]
        return cached

    cached = _PAYMENT_METHOD_CACHE.get(None)
    if cached is None:
        cached = {}
        _PAYMENT_METHOD_CACHE.set(cached)
    return cached


def ensure_stripe_customer(
    user: User,
    *,
    customer_id: str | None = None,
    cache_scope: object | None = None,
) -> str:
    """
    Return an existing Stripe Customer ID for the user, creating one if necessary.

    - Request-scoped cache avoids multiple Stripe Customer.retrieve calls per request.
    - A verification timestamp throttles revalidation of existing customer IDs.
    """
    stripe.api_key = _get_stripe_api_key()
    cache_key = getattr(user, "pk", None)
    cache = _get_customer_cache(cache_scope)
    if cache_key is not None:
        cached_value = cache.get(int(cache_key))
        if cached_value:
            return cached_value

    stored_id = (getattr(user, "stripe_customer_id", "") or "").strip()
    candidate_id = (customer_id or stored_id or "").strip()
    now = timezone.now()
    verified_at = getattr(user, "stripe_customer_verified_at", None)
    needs_verification = bool(candidate_id) and (
        verified_at is None or (now - verified_at) > CUSTOMER_VERIFY_TTL
    )

    if candidate_id and needs_verification:
        try:
            _log_stripe_call("customer.retrieve", user_id=user.id)
            stripe.Customer.retrieve(candidate_id)
            verified_at = now
        except stripe.error.InvalidRequestError:
            logger.info("Stripe customer %s missing; recreating.", candidate_id)
            candidate_id = ""
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    if not candidate_id:
        try:
            _log_stripe_call("customer.create", user_id=user.id)
            customer = stripe.Customer.create(
                email=user.email or None,
                name=(user.get_full_name() or user.username or f"user-{user.id}"),
                metadata={"user_id": str(user.id)},
            )
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)
        candidate_id = customer.id
        verified_at = now

    update_fields: list[str] = []
    if candidate_id and candidate_id != stored_id:
        user.stripe_customer_id = candidate_id
        update_fields.append("stripe_customer_id")
    if verified_at and verified_at != getattr(user, "stripe_customer_verified_at", None):
        user.stripe_customer_verified_at = verified_at
        update_fields.append("stripe_customer_verified_at")
    if update_fields:
        user.save(update_fields=update_fields)

    if cache_key is not None and candidate_id:
        cache[int(cache_key)] = candidate_id

    return candidate_id


def _setup_intent_fields(payload: Any) -> tuple[str, str, str]:
    """Extract id, client_secret, and status from a Stripe SetupIntent payload."""
    intent_id = getattr(payload, "id", None)
    if intent_id is None and hasattr(payload, "get"):
        intent_id = payload.get("id")
    client_secret = getattr(payload, "client_secret", None)
    if client_secret is None and hasattr(payload, "get"):
        client_secret = payload.get("client_secret")
    status = getattr(payload, "status", None)
    if status is None and hasattr(payload, "get"):
        status = payload.get("status")
    return (intent_id or "").strip(), (client_secret or "").strip(), (status or "").strip()


def create_or_reuse_setup_intent(
    *,
    user: User,
    intent_type: str = PaymentSetupIntent.IntentType.DEFAULT_CARD,
    cache_scope: object | None = None,
) -> PaymentSetupIntent:
    """
    Return an open SetupIntent for the given user/intent_type, creating one if needed.

    Reuses a recent, still-open intent without hitting Stripe. Otherwise, refreshes its
    status if stale before creating a new one.
    """
    stripe.api_key = _get_stripe_api_key()
    customer_id = ensure_stripe_customer(user, cache_scope=cache_scope)
    now = timezone.now()
    existing = (
        PaymentSetupIntent.objects.filter(
            user=user,
            intent_type=intent_type,
            consumed_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )

    if existing:
        age = now - (existing.updated_at or existing.created_at)
        if existing.status in OPEN_SETUP_INTENT_STATUSES and age < SETUP_INTENT_REFRESH_AGE:
            return existing

        if existing.status in OPEN_SETUP_INTENT_STATUSES:
            try:
                _log_stripe_call(
                    "setup_intent.retrieve",
                    intent_type=intent_type,
                    user_id=user.id,
                )
                refreshed = stripe.SetupIntent.retrieve(existing.stripe_setup_intent_id)
                intent_id, client_secret, status = _setup_intent_fields(refreshed)
                status = status or existing.status
                if status in OPEN_SETUP_INTENT_STATUSES:
                    updates = []
                    if status != existing.status:
                        existing.status = status
                        updates.append("status")
                    if client_secret and client_secret != existing.client_secret:
                        existing.client_secret = client_secret
                        updates.append("client_secret")
                    if updates:
                        existing.save(update_fields=updates)
                    return existing

                existing.status = status or existing.status
                existing.consumed_at = existing.consumed_at or now
                existing.save(update_fields=["status", "consumed_at"])
            except stripe.error.InvalidRequestError:
                existing.status = "canceled"
                existing.consumed_at = existing.consumed_at or now
                existing.save(update_fields=["status", "consumed_at"])
            except stripe.error.StripeError as exc:
                _handle_stripe_error(exc)

    try:
        _log_stripe_call("setup_intent.create", intent_type=intent_type, user_id=user.id)
        setup_intent = stripe.SetupIntent.create(
            customer=customer_id,
            payment_method_types=["card"],
            usage="off_session",
            metadata={
                "user_id": str(user.id),
                "intent_type": intent_type,
                "env": getattr(settings, "STRIPE_ENV", "dev") or "dev",
            },
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    intent_id, client_secret, status = _setup_intent_fields(setup_intent)
    if not intent_id or not client_secret:
        raise StripeConfigurationError("Stripe did not return a SetupIntent client secret.")

    return PaymentSetupIntent.objects.create(
        user=user,
        intent_type=intent_type,
        stripe_setup_intent_id=intent_id,
        client_secret=client_secret,
        status=status or "requires_confirmation",
    )


def _ensure_payment_method_for_customer(
    payment_method_id: str,
    customer_id: str,
    *,
    attached_via_setup_intent: bool = False,
    cache_scope: object | None = None,
) -> None:
    """Attach the payment method to the Stripe customer if not already linked."""
    if not payment_method_id or not customer_id:
        return
    if attached_via_setup_intent:
        return

    stripe.api_key = _get_stripe_api_key()
    cache = _get_payment_method_cache(cache_scope)
    payment_method = cache.get(payment_method_id)
    if payment_method is None:
        try:
            _log_stripe_call("payment_method.retrieve", customer_id=customer_id)
            payment_method = stripe.PaymentMethod.retrieve(payment_method_id)
            cache[payment_method_id] = payment_method
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)
    attached_customer = getattr(payment_method, "customer", None)
    if attached_customer == customer_id:
        return
    if attached_customer and attached_customer != customer_id:
        try:
            _log_stripe_call("payment_method.detach", customer_id=attached_customer)
            stripe.PaymentMethod.detach(payment_method_id)
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)
    try:
        _log_stripe_call("payment_method.attach", customer_id=customer_id)
        attached_pm = stripe.PaymentMethod.attach(payment_method_id, customer=customer_id)
        cache[payment_method_id] = attached_pm
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)


def fetch_payment_method_details(
    payment_method_id: str,
    *,
    cache_scope: object | None = None,
) -> dict[str, object]:
    """Return brand/last4/exp_month/exp_year for a Stripe PaymentMethod."""
    if not payment_method_id:
        raise StripePaymentError("payment_method_id is required.")

    stripe.api_key = _get_stripe_api_key()
    cache = _get_payment_method_cache(cache_scope)
    pm = cache.get(payment_method_id)
    if pm is None:
        try:
            _log_stripe_call("payment_method.retrieve", customer_id=None)
            pm = stripe.PaymentMethod.retrieve(payment_method_id)
            cache[payment_method_id] = pm
        except stripe.error.StripeError as exc:
            _handle_stripe_error(exc)

    card = getattr(pm, "card", None) or getattr(pm, "card", {}) or {}
    if hasattr(card, "get"):
        card_dict = card
    else:
        # stripe objects behave like dicts
        card_dict = dict(card)

    return {
        "brand": (card_dict.get("brand") or "").upper(),
        "last4": card_dict.get("last4") or "",
        "exp_month": card_dict.get("exp_month"),
        "exp_year": card_dict.get("exp_year"),
    }


def charge_promotion_payment(
    *,
    owner: User,
    amount_cents: int,
    payment_method_id: str,
    customer_id: str,
    attached_via_setup_intent: bool = False,
    cache_scope: object | None = None,
    metadata: dict[str, str] | None = None,
) -> str:
    """Charge a promotion amount immediately using Stripe PaymentIntents."""
    if amount_cents <= 0:
        raise StripePaymentError("Promotion total must be greater than zero.")

    stripe.api_key = _get_stripe_api_key()
    _ensure_payment_method_for_customer(
        payment_method_id,
        customer_id,
        attached_via_setup_intent=attached_via_setup_intent,
        cache_scope=cache_scope,
    )

    metadata_payload = {
        "env": getattr(settings, "STRIPE_ENV", "dev") or "dev",
        "kind": "promotion_payment",
        "owner_id": str(owner.id),
    }
    if metadata:
        metadata_payload.update(metadata)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency="cad",
            customer=customer_id,
            payment_method=payment_method_id,
            confirm=True,
            off_session=False,
            automatic_payment_methods={**AUTOMATIC_PAYMENT_METHODS_CONFIG},
            metadata=metadata_payload,
        )
    except stripe.error.StripeError as exc:
        _handle_stripe_error(exc)

    return intent.id


def _log_owner_payout_event(*, event_type: str, data_object: dict, account_id: str) -> None:
    if event_type != "payout.paid":
        return
    if not account_id:
        return

    payout_id = data_object.get("id") or ""
    if not payout_id:
        return

    if Transaction.objects.filter(
        stripe_id=str(payout_id),
        kind__in=[Transaction.Kind.OWNER_PAYOUT, Transaction.Kind.OWNER_EARNING],
        booking__isnull=True,
        amount__lt=0,
    ).exists():
        return

    payout_account = (
        OwnerPayoutAccount.objects.filter(stripe_account_id=account_id)
        .select_related("user")
        .first()
    )
    if payout_account is None:
        return

    amount_cents = data_object.get("amount")
    if amount_cents is None:
        return

    try:
        amount = (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return

    if amount <= Decimal("0"):
        return

    currency = (data_object.get("currency") or "cad").lower()
    log_transaction(
        user=payout_account.user,
        booking=None,
        promotion_slot=None,
        kind=Transaction.Kind.OWNER_PAYOUT,
        amount=-amount,
        currency=currency,
        stripe_id=str(payout_id),
    )


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

    account_id = event.get("account") or data_object.get("account") or ""
    account_data: Any | None = None
    if account_id:
        try:
            account_data = _retrieve_account_with_expand(account_id)
            _handle_connect_account_updated_event(account_data)
        except StripeConfigurationError:
            logger.warning("stripe_webhook: missing Stripe config for account sync")
        except stripe.error.StripeError as exc:  # noqa: PERF203
            logger.warning(
                "stripe_webhook: failed to sync connect account",
                extra={"account_id": account_id, "error": str(exc)},
            )

    if event_type == "payout.paid":
        _log_owner_payout_event(
            event_type=event_type,
            data_object=data_object,
            account_id=account_id,
        )
        return Response(status=status.HTTP_200_OK)

    if event_type == "account.updated":
        if account_data is not None:
            return Response(status=status.HTTP_200_OK)
        _handle_connect_account_updated_event(data_object)
        return Response(status=status.HTTP_200_OK)

    if event_type == "identity.verification_session.verified":
        user_id = metadata.get("user_id")
        session_id = data_object.get("id")
        if not user_id or not session_id:
            return Response(status=status.HTTP_200_OK)
        try:
            user = User.objects.get(pk=int(user_id))
        except (User.DoesNotExist, ValueError, TypeError):
            return Response(status=status.HTTP_200_OK)

        IdentityVerification.objects.update_or_create(
            user=user,
            session_id=session_id,
            defaults={
                "status": IdentityVerification.Status.VERIFIED,
                "verified_at": timezone.now(),
                "last_error_code": "",
                "last_error_reason": "",
            },
        )
        logger.info(
            "Stripe identity session verified",
            extra={"user_id": user.id, "session_id": session_id},
        )
        return Response(status=status.HTTP_200_OK)

    if event_type == "account.updated":
        _handle_connect_account_updated_event(data_object)
        return Response(status=status.HTTP_200_OK)

    if event_type == "checkout.session.completed":
        session_metadata = metadata or {}
        if session_metadata.get("kind") != "promotion_slot":
            session_id = data_object.get("id", "")
            session_url = data_object.get("url", "") or ""
            if session_id:
                PromotionCheckoutSession.objects.filter(stripe_session_id=session_id).update(
                    status="completed",
                    session_url=session_url or None,
                    consumed_at=timezone.now(),
                )
            return Response(status=status.HTTP_200_OK)
        session_id = data_object.get("id", "")
        session_url = data_object.get("url", "") or ""
        if not session_id:
            logger.warning("stripe_webhook: promotion session missing id")
            return Response(status=status.HTTP_200_OK)
        PromotionCheckoutSession.objects.filter(stripe_session_id=session_id).update(
            status="completed",
            session_url=session_url or None,
            consumed_at=timezone.now(),
        )
        slot = (
            PromotedSlot.objects.filter(stripe_session_id=session_id)
            .select_related("listing")
            .first()
        )
        if slot is None:
            logger.info("stripe_webhook: no promoted slot for session %s", session_id)
            return Response(status=status.HTTP_200_OK)
        if slot.active:
            return Response(status=status.HTTP_200_OK)

        updated_fields = ["active", "updated_at"]
        current_tz = timezone.get_current_timezone()

        if slot.starts_at is None:
            start_value = session_metadata.get("starts_at")
            if start_value:
                try:
                    parsed_start = datetime.fromisoformat(start_value)
                    if parsed_start.tzinfo is None:
                        parsed_start = timezone.make_aware(parsed_start, current_tz)
                    else:
                        parsed_start = parsed_start.astimezone(current_tz)
                    slot.starts_at = parsed_start
                except (TypeError, ValueError):
                    slot.starts_at = timezone.now()
            else:
                slot.starts_at = timezone.now()
            updated_fields.append("starts_at")

        if slot.ends_at is None:
            end_value = session_metadata.get("ends_at")
            if end_value:
                try:
                    parsed_end = datetime.fromisoformat(end_value)
                    if parsed_end.tzinfo is None:
                        parsed_end = timezone.make_aware(parsed_end, current_tz)
                    else:
                        parsed_end = parsed_end.astimezone(current_tz)
                    slot.ends_at = parsed_end
                except (TypeError, ValueError):
                    slot.ends_at = slot.starts_at + timedelta(days=1)
            else:
                slot.ends_at = slot.starts_at + timedelta(days=1)
            updated_fields.append("ends_at")

        slot.active = True
        slot.save(update_fields=updated_fields)
        return Response(status=status.HTTP_200_OK)

    if event_type == "payment_intent.succeeded" and booking_id and kind == "booking_charge":
        try:
            booking = Booking.objects.get(pk=int(booking_id))
        except (Booking.DoesNotExist, ValueError):
            return Response(status=status.HTTP_200_OK)

        intent_id = data_object.get("id", "") or booking.charge_payment_intent_id
        if booking.status in {Booking.Status.REQUESTED, Booking.Status.CONFIRMED}:
            booking.status = Booking.Status.PAID
            booking.charge_payment_intent_id = intent_id or booking.charge_payment_intent_id
            booking.save(update_fields=["status", "charge_payment_intent_id", "updated_at"])
        if getattr(settings, "STRIPE_BOOKINGS_DESTINATION_CHARGES", True):
            try:
                fees = _extract_booking_fees(booking)
            except StripePaymentError as exc:
                logger.warning(
                    "stripe_webhook: booking fee data invalid for booking %s: %s",
                    booking.id,
                    str(exc) or "fee error",
                )
                return Response(status=status.HTTP_200_OK)

            owner_payout = fees["owner_payout"]
            platform_fee_total = fees["platform_fee_total"]
            owner = booking.owner

            owner_stripe_id = _extract_transfer_id_from_intent(data_object)
            if not owner_stripe_id and intent_id:
                intent_payload = _retrieve_intent_with_transfer(intent_id)
                if intent_payload is not None:
                    owner_stripe_id = _extract_transfer_id_from_intent(intent_payload)

            if owner_payout > Decimal("0"):
                owner_txns = Transaction.objects.filter(
                    user=owner,
                    booking=booking,
                    kind=Transaction.Kind.OWNER_EARNING,
                )
                owner_txn_exists = False
                if owner_stripe_id:
                    owner_txn_exists = owner_txns.filter(stripe_id=owner_stripe_id).exists()
                if intent_id and not owner_txn_exists:
                    owner_txn_exists = owner_txns.filter(stripe_id=intent_id).exists()
                if not owner_txn_exists:
                    owner_txn_exists = owner_txns.filter(amount=owner_payout).exists()
                if not owner_txn_exists:
                    log_transaction(
                        user=owner,
                        booking=booking,
                        kind=Transaction.Kind.OWNER_EARNING,
                        amount=owner_payout,
                        stripe_id=owner_stripe_id or intent_id or None,
                    )

            if platform_fee_total > Decimal("0"):
                from payments_refunds import get_platform_ledger_user

                platform_user = get_platform_ledger_user()
                if platform_user is not None:
                    platform_txn_exists = Transaction.objects.filter(
                        user=platform_user,
                        booking=booking,
                        kind=Transaction.Kind.PLATFORM_FEE,
                        amount=platform_fee_total,
                    ).exists()
                    if not platform_txn_exists:
                        log_transaction(
                            user=platform_user,
                            booking=booking,
                            kind=Transaction.Kind.PLATFORM_FEE,
                            amount=platform_fee_total,
                        )
                else:
                    logger.info(
                        "stripe_webhook: platform fee not logged; platform ledger user missing."
                    )
                _maybe_update_application_fee_description(
                    booking_id=booking.id,
                    intent_payload=data_object,
                    intent_id=intent_id or None,
                )

    return Response(status=status.HTTP_200_OK)
