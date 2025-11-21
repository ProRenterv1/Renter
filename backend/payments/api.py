"""Owner payouts API endpoints."""

from __future__ import annotations

import logging
from datetime import timezone as datetime_timezone
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .ledger import compute_owner_balances, get_owner_earnings_queryset
from .models import OwnerPayoutAccount
from .stripe_api import create_connect_onboarding_link, ensure_connect_account

logger = logging.getLogger(__name__)
STRIPE_ERROR_NAMES = {
    "StripeConfigurationError",
    "StripePaymentError",
    "StripeTransientError",
}
ONBOARDING_ERROR_MESSAGE = "Stripe onboarding is temporarily unavailable. Please try again later."


def _is_stripe_api_error(exc: Exception) -> bool:
    """Return True if the exception matches a known Stripe error by name."""
    return exc.__class__.__name__ in STRIPE_ERROR_NAMES


DEFAULT_HISTORY_LIMIT = 50
MAX_HISTORY_LIMIT = 200


def _default_requirements() -> dict:
    return {
        "currently_due": [],
        "eventually_due": [],
        "past_due": [],
        "disabled_reason": None,
    }


def _format_money(value: Decimal) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def _normalize_requirements(data: dict | None) -> dict:
    payload = _default_requirements()
    if data:
        payload["currently_due"] = list(data.get("currently_due") or [])
        payload["eventually_due"] = list(data.get("eventually_due") or [])
        payload["past_due"] = list(data.get("past_due") or [])
        disabled = data.get("disabled_reason")
        payload["disabled_reason"] = disabled or None
    return payload


def _connect_payload(payout_account: OwnerPayoutAccount | None) -> dict:
    if payout_account is None:
        return {
            "has_account": False,
            "stripe_account_id": None,
            "payouts_enabled": False,
            "charges_enabled": False,
            "is_fully_onboarded": False,
            "requirements_due": _default_requirements(),
        }
    requirements = _normalize_requirements(payout_account.requirements_due or {})
    return {
        "has_account": True,
        "stripe_account_id": payout_account.stripe_account_id,
        "payouts_enabled": payout_account.payouts_enabled,
        "charges_enabled": payout_account.charges_enabled,
        "is_fully_onboarded": payout_account.is_fully_onboarded,
        "requirements_due": requirements,
    }


def _serialize_datetime(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        aware = timezone.make_aware(dt, datetime_timezone.utc)
    else:
        aware = dt.astimezone(datetime_timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


def _parse_limit(value: str | None) -> int:
    if not value:
        return DEFAULT_HISTORY_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("limit must be an integer.")
    if parsed <= 0:
        raise ValueError("limit must be greater than zero.")
    return min(parsed, MAX_HISTORY_LIMIT)


def _parse_offset(value: str | None) -> int:
    if not value:
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("offset must be an integer.")
    if parsed < 0:
        raise ValueError("offset must be greater than or equal to zero.")
    return parsed


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_payouts_summary(request):
    """Return connect onboarding state + ledger balances for an owner."""
    user = request.user
    payout_account: OwnerPayoutAccount | None = None
    try:
        payout_account = ensure_connect_account(user)
    except Exception as exc:
        if _is_stripe_api_error(exc):
            logger.warning("payments: ensure_connect_account failed for user %s: %s", user.id, exc)
            payout_account = None
        else:
            raise
    balances = compute_owner_balances(user)
    return Response(
        {
            "connect": _connect_payload(payout_account),
            "balances": balances,
        }
    )


def _history_direction(amount: Decimal) -> str:
    if amount < Decimal("0"):
        return "debit"
    return "credit"


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_payouts_history(request):
    """Return paginated ledger rows for owner earnings."""
    qs = get_owner_earnings_queryset(request.user).select_related("booking__listing")
    kind_param = request.query_params.get("kind")
    if kind_param:
        qs = qs.filter(kind=kind_param)

    try:
        limit = _parse_limit(request.query_params.get("limit"))
        offset = _parse_offset(request.query_params.get("offset"))
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    total_count = qs.count()
    sliced = qs[offset : offset + limit]

    results = []
    for tx in sliced:
        booking = getattr(tx, "booking", None)
        listing = getattr(booking, "listing", None) if booking else None
        amount = Decimal(tx.amount)
        results.append(
            {
                "id": tx.id,
                "created_at": _serialize_datetime(tx.created_at),
                "kind": tx.kind,
                "amount": _format_money(amount),
                "currency": (tx.currency or "").upper(),
                "booking_id": getattr(booking, "id", None),
                "booking_status": getattr(booking, "status", None),
                "listing_title": getattr(listing, "title", None),
                "direction": _history_direction(amount),
            }
        )

    next_offset = offset + limit
    if next_offset >= total_count:
        next_offset = None

    return Response(
        {
            "results": results,
            "count": total_count,
            "next_offset": next_offset,
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def owner_payouts_start_onboarding(request):
    """Return a Stripe Connect onboarding link for the owner."""
    user = request.user
    try:
        onboarding_url = create_connect_onboarding_link(user)
    except Exception as exc:
        if _is_stripe_api_error(exc):
            logger.warning("payments: onboarding link failure for user %s: %s", user.id, exc)
            return Response(
                {"detail": ONBOARDING_ERROR_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise

    try:
        payout_account = user.payout_account
    except OwnerPayoutAccount.DoesNotExist:
        try:
            payout_account = ensure_connect_account(user)
        except Exception as exc:
            if _is_stripe_api_error(exc):
                payout_account = None
            else:
                raise

    stripe_account_id = payout_account.stripe_account_id if payout_account else None
    return Response(
        {
            "onboarding_url": onboarding_url,
            "stripe_account_id": stripe_account_id,
        }
    )
