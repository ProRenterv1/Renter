"""Owner payouts API endpoints."""

from __future__ import annotations

import logging
from datetime import timezone as datetime_timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from payments.tax import compute_gst, platform_gst_enabled, platform_gst_rate
from storage.s3 import presign_get

from .ledger import (
    compute_owner_available_balance,
    compute_owner_balances,
    get_owner_history_queryset,
    log_transaction,
)
from .models import OwnerFeeTaxInvoice, OwnerPayoutAccount, Transaction
from .stripe_api import (
    create_connect_onboarding_session,
    create_instant_payout,
    ensure_connect_account,
    get_connect_available_balance,
    transfer_earnings_to_platform,
    update_connect_bank_account,
)

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


def collect_due(requirements: dict | None) -> set[str]:
    due_fields: set[str] = set()
    if not requirements:
        return due_fields
    for key in ("currently_due", "past_due"):
        for field in requirements.get(key) or []:
            if field:
                due_fields.add(str(field))
    return due_fields


def is_id_requirement(field: str | None) -> bool:
    if not field:
        return False
    prefixes = (
        "individual.verification.",
        "company.verification.",
        "person.verification.",
    )
    if any(field.startswith(prefix) for prefix in prefixes):
        return True
    return ".verification.document" in field or ".verification.additional_document" in field


def is_personal_requirement(field: str | None) -> bool:
    if not field or is_id_requirement(field):
        return False
    personal_prefixes = (
        "individual.",
        "company.",
        "business_profile.",
        "external_account",
        "tos_acceptance",
    )
    return any(field.startswith(prefix) for prefix in personal_prefixes)


def compute_kyc_steps(requirements: dict | None, is_fully_onboarded: bool) -> dict:
    due = collect_due(requirements)
    id_due = sorted([field for field in due if is_id_requirement(field)])
    personal_due = sorted([field for field in due if is_personal_requirement(field)])

    personal_complete = len(personal_due) == 0
    id_required = len(id_due) > 0
    id_submitted_pending = personal_complete and (not id_required) and (not is_fully_onboarded)
    kyc_locked = id_submitted_pending

    return {
        "personal_complete": personal_complete,
        "id_required": id_required,
        "id_submitted_pending": id_submitted_pending,
        "kyc_locked": kyc_locked,
        "personal_due": personal_due,
        "id_due": id_due,
    }


def _connect_payload(payout_account: OwnerPayoutAccount | None) -> dict:
    if payout_account is None:
        return {
            "has_account": False,
            "stripe_account_id": None,
            "payouts_enabled": False,
            "charges_enabled": False,
            "is_fully_onboarded": False,
            "requirements_due": _default_requirements(),
            "bank_details": None,
            "lifetime_instant_payouts": "0.00",
            "business_type": "individual",
            "kyc_steps": {
                "personal_complete": False,
                "id_required": False,
                "id_submitted_pending": False,
                "kyc_locked": False,
                "personal_due": [],
                "id_due": [],
            },
        }
    requirements = _normalize_requirements(payout_account.requirements_due or {})
    kyc_steps = compute_kyc_steps(requirements, payout_account.is_fully_onboarded)
    acct_last4 = (payout_account.account_number or "")[-4:]
    return {
        "has_account": True,
        "stripe_account_id": payout_account.stripe_account_id,
        "payouts_enabled": payout_account.payouts_enabled,
        "charges_enabled": payout_account.charges_enabled,
        "is_fully_onboarded": payout_account.is_fully_onboarded,
        "business_type": getattr(payout_account, "business_type", "individual") or "individual",
        "requirements_due": requirements,
        "kyc_steps": kyc_steps,
        "lifetime_instant_payouts": _format_money(
            getattr(payout_account, "lifetime_instant_payouts", Decimal("0.00")) or Decimal("0.00")
        ),
        "bank_details": {
            "transit_number": payout_account.transit_number or "",
            "institution_number": payout_account.institution_number or "",
            "account_last4": acct_last4 or "",
        },
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


def _parse_history_scope(value: str | None) -> str | None:
    if value is None:
        return None
    scope = str(value).strip().lower()
    if scope not in {"owner", "all"}:
        raise ValueError("scope must be 'owner' or 'all'.")
    return scope


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
    available = compute_owner_available_balance(user)
    balances["available_earnings"] = _format_money(available)

    connect_available = None
    if payout_account is not None:
        connect_available = get_connect_available_balance(payout_account)
    if connect_available is not None:
        balances["connect_available_earnings"] = _format_money(connect_available)
    else:
        balances["connect_available_earnings"] = None
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
    user = request.user
    is_owner = bool(getattr(user, "can_list", False))
    try:
        scope = _parse_history_scope(request.query_params.get("scope"))
    except ValueError:
        logger.warning(
            "Invalid scope param for owner payouts history",
            extra={"user_id": getattr(user, "id", None)},
            exc_info=True,
        )
        return Response({"detail": "Invalid scope parameter."}, status=status.HTTP_400_BAD_REQUEST)

    if scope == "all":
        qs = Transaction.objects.filter(user=user).exclude(
            kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        )
    elif scope == "owner":
        qs = get_owner_history_queryset(user)
    elif is_owner:
        qs = get_owner_history_queryset(user)
    else:
        # For renters, show their charges/refunds but hide deposit holds.
        qs = Transaction.objects.filter(user=user).exclude(
            kind=Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
        )
    qs = qs.select_related("booking__listing")
    kind_param = request.query_params.get("kind")
    if kind_param:
        qs = qs.filter(kind=kind_param)

    try:
        limit = _parse_limit(request.query_params.get("limit"))
        offset = _parse_offset(request.query_params.get("offset"))
    except ValueError:
        logger.warning(
            "Invalid pagination params for owner payouts history",
            extra={"user_id": getattr(user, "id", None)},
            exc_info=True,
        )
        return Response(
            {"detail": "Invalid pagination parameters."}, status=status.HTTP_400_BAD_REQUEST
        )

    total_count = qs.count()
    sliced = qs[offset : offset + limit]

    results = []
    for tx in sliced:
        booking = getattr(tx, "booking", None)
        listing = getattr(booking, "listing", None) if booking else None
        amount = Decimal(tx.amount)
        direction = _history_direction(amount)

        if tx.kind == Transaction.Kind.BOOKING_CHARGE and amount > 0:
            direction = "debit"
            amount = -abs(amount)
        elif tx.kind == Transaction.Kind.PROMOTION_CHARGE and amount > 0:
            direction = "debit"
            amount = -abs(amount)
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
                "direction": direction,
                "stripe_id": getattr(tx, "stripe_id", None),
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


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_fee_invoices_list(request):
    invoices = OwnerFeeTaxInvoice.objects.filter(owner=request.user).order_by("-period_start")
    data = [
        {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "period_start": invoice.period_start.isoformat(),
            "period_end": invoice.period_end.isoformat(),
            "fee_subtotal": _format_money(invoice.fee_subtotal),
            "gst": _format_money(invoice.gst),
            "total": _format_money(invoice.total),
            "created_at": invoice.created_at.isoformat(),
        }
        for invoice in invoices
    ]
    return Response({"results": data})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def owner_fee_invoice_download(request, invoice_id: int):
    invoice = OwnerFeeTaxInvoice.objects.filter(owner=request.user, pk=invoice_id).first()
    if invoice is None:
        return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
    if not invoice.pdf_s3_key:
        return Response(
            {"detail": "Invoice PDF not available yet."},
            status=status.HTTP_404_NOT_FOUND,
        )

    presign = presign_get(invoice.pdf_s3_key, response_content_type="application/pdf")
    return Response({"url": presign["url"], "headers": presign.get("headers", {})})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def owner_payouts_start_onboarding(request):
    """Return Stripe Connect onboarding session details (with legacy link fallback)."""
    user = request.user
    data = request.data or {}
    business_type = (data.get("business_type") or "").strip().lower()
    if business_type and business_type not in {"individual", "company"}:
        return Response(
            {"business_type": ["Must be 'individual' or 'company'."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    business_type_value = business_type or None
    try:
        session_payload = create_connect_onboarding_session(user, business_type=business_type_value)
    except TypeError:
        # Defensive: allow monkeypatched or legacy callers that ignore business_type.
        try:
            session_payload = create_connect_onboarding_session(user)
        except Exception as exc:
            if _is_stripe_api_error(exc):
                logger.warning("payments: onboarding link failure for user %s: %s", user.id, exc)
                return Response(
                    {"detail": ONBOARDING_ERROR_MESSAGE},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            raise
    except Exception as exc:
        if _is_stripe_api_error(exc):
            logger.warning("payments: onboarding link failure for user %s: %s", user.id, exc)
            return Response(
                {"detail": ONBOARDING_ERROR_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise
    return Response(session_payload)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def owner_payouts_update_bank_details(request):
    """
    Create/update the owner payout bank details for the authenticated user.
    Fields: transit_number, institution_number, account_number.
    """
    user = request.user
    data = request.data or {}
    transit = (data.get("transit_number") or "").strip()
    institution = (data.get("institution_number") or "").strip()
    account = (data.get("account_number") or "").strip()

    errors = {}
    if not transit:
        errors["transit_number"] = ["This field is required."]
    if not institution:
        errors["institution_number"] = ["This field is required."]
    if not account:
        errors["account_number"] = ["This field is required."]

    if errors:
        return Response(errors, status=status.HTTP_400_BAD_REQUEST)

    try:
        payout_account = ensure_connect_account(user)
    except Exception as exc:
        if _is_stripe_api_error(exc):
            return Response(
                {"detail": ONBOARDING_ERROR_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise

    try:
        bank_obj = update_connect_bank_account(
            payout_account=payout_account,
            transit_number=transit,
            institution_number=institution,
            account_number=account,
        )
    except Exception as exc:
        if _is_stripe_api_error(exc):
            return Response(
                {
                    "detail": (
                        "Unable to validate bank account. Please check your details and try again."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        raise

    last4 = ""
    if hasattr(bank_obj, "get"):
        last4 = str(bank_obj.get("last4") or "")
    elif hasattr(bank_obj, "last4"):
        last4 = str(bank_obj.last4 or "")

    payout_account.transit_number = transit
    payout_account.institution_number = institution
    payout_account.account_number = last4 or (account[-4:] if account else "")
    payout_account.last_synced_at = timezone.now()
    payout_account.save(
        update_fields=[
            "transit_number",
            "institution_number",
            "account_number",
            "last_synced_at",
        ]
    )

    return Response({"connect": _connect_payload(payout_account)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def owner_payouts_instant_payout(request):
    """
    Preview or execute an instant payout.

    Request:
      - POST with no body or {"confirm": false}  -> preview only
      - POST with {"confirm": true}             -> execute payout

    Response (preview):
      {
        "executed": false,
        "currency": "cad",
        "amount_before_fee": "123.45",
        "amount_after_fee": "119.75"
      }

    Response (execute):
      {
        "ok": true,
        "executed": true,
        "currency": "cad",
        "amount_before_fee": "123.45",
        "amount_after_fee": "119.75",
        "stripe_payout_id": "po_...",
      }
    """
    user = request.user
    data = request.data or {}
    confirm = bool(data.get("confirm"))

    # 1) Ensure owner has a Connect account
    try:
        payout_account = ensure_connect_account(user)
    except Exception as exc:
        if _is_stripe_api_error(exc):
            return Response(
                {"detail": ONBOARDING_ERROR_MESSAGE},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise

    # 2) Require local bank details to be present in payout_account
    if not (
        payout_account.transit_number
        and payout_account.institution_number
        and payout_account.account_number
    ):
        return Response(
            {"detail": "Add your bank details before requesting an instant payout."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 3) Compute available balance directly from the ledger
    try:
        available = compute_owner_available_balance(user)
    except (InvalidOperation, Exception):
        return Response(
            {"detail": "Unable to compute available balance for instant payout."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if available <= Decimal("0.00"):
        return Response(
            {"detail": "No earnings available for instant payout."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    fee_rate = getattr(settings, "INSTANT_PAYOUT_FEE_RATE", Decimal("0.03"))
    fee_base = (available * fee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    fee_gst = compute_gst(fee_base)
    total_fee = (fee_base + fee_gst).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    net = available - total_fee
    if net <= Decimal("0.00"):
        return Response(
            {"detail": "Instant payout amount is too small after fees."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    amount_before_fee = available.quantize(Decimal("0.01"))
    amount_after_fee = net.quantize(Decimal("0.01"))

    # 4) Preview-only branch
    if not confirm:
        return Response(
            {
                "executed": False,
                "currency": "cad",
                "amount_before_fee": str(amount_before_fee),
                "fee_base": str(fee_base),
                "fee_gst": str(fee_gst),
                "amount_after_fee": str(amount_after_fee),
            }
        )

    # 5) Execute payout
    amount_cents = int((amount_after_fee * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    if amount_cents <= 0:
        return Response(
            {"detail": "Instant payout amount is too small."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        payout = create_instant_payout(
            user=user,
            payout_account=payout_account,
            amount_cents=amount_cents,
            metadata={
                "amount_before_fee": str(amount_before_fee),
                "fee_base": str(fee_base),
                "fee_gst": str(fee_gst),
                "fee_total": str(total_fee),
                "gst_enabled": str(platform_gst_enabled()),
                "gst_rate": str(platform_gst_rate()),
            },
        )
    except Exception as exc:
        if _is_stripe_api_error(exc):
            return Response(
                {"detail": "Stripe temporarily unavailable. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise

    stripe_payout_id = getattr(payout, "id", None)
    if not stripe_payout_id and hasattr(payout, "get"):
        stripe_payout_id = payout.get("id")  # type: ignore[arg-type]

    fee_transfer_id: str | None = None
    if total_fee > Decimal("0"):
        fee_cents = int((total_fee * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        try:
            fee_transfer_id = transfer_earnings_to_platform(
                payout_account=payout_account,
                amount_cents=fee_cents,
                metadata={
                    "kind": "instant_payout_fee",
                    "payout_id": str(stripe_payout_id or ""),
                    "amount_before_fee": str(amount_before_fee),
                    "amount_after_fee": str(amount_after_fee),
                    "fee_base": str(fee_base),
                    "fee_gst": str(fee_gst),
                    "fee_total": str(total_fee),
                    "gst_enabled": str(platform_gst_enabled()),
                    "gst_rate": str(platform_gst_rate()),
                },
            )
        except Exception as exc:
            if _is_stripe_api_error(exc):
                logger.warning(
                    "payments: instant payout fee transfer failed for user %s: %s",
                    user.id,
                    exc,
                )
            else:
                raise

    # Update cumulative instant payout tracking
    already_paid = Decimal(getattr(payout_account, "lifetime_instant_payouts", "0.00") or "0.00")
    payout_account.lifetime_instant_payouts = (already_paid + available).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )
    payout_account.last_synced_at = timezone.now()
    payout_account.save(update_fields=["lifetime_instant_payouts", "last_synced_at"])

    # Log owner payout transaction (negative) and platform fee (positive)
    log_transaction(
        user=user,
        booking=None,
        promotion_slot=None,
        kind=Transaction.Kind.OWNER_PAYOUT,
        amount=-amount_before_fee,
        currency="cad",
        stripe_id=stripe_payout_id,
    )
    log_transaction(
        user=user,
        booking=None,
        promotion_slot=None,
        kind=Transaction.Kind.PLATFORM_FEE,
        amount=fee_base,
        currency="cad",
        stripe_id=fee_transfer_id or stripe_payout_id,
    )
    if fee_gst > Decimal("0"):
        log_transaction(
            user=user,
            booking=None,
            promotion_slot=None,
            kind=Transaction.Kind.GST_COLLECTED,
            amount=fee_gst,
            currency="cad",
            stripe_id=fee_transfer_id or stripe_payout_id,
        )

    return Response(
        {
            "ok": True,
            "executed": True,
            "currency": "cad",
            "amount_before_fee": str(amount_before_fee),
            "fee_base": str(fee_base),
            "fee_gst": str(fee_gst),
            "amount_after_fee": str(amount_after_fee),
            "stripe_payout_id": stripe_payout_id,
        },
        status=status.HTTP_202_ACCEPTED,
    )
