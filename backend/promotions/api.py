from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from listings.models import Listing
from notifications import tasks as notification_tasks
from payments.ledger import compute_owner_available_balance, log_transaction
from payments.models import Transaction
from payments.stripe_api import (
    StripeConfigurationError,
    StripePaymentError,
    StripeTransientError,
    charge_promotion_payment,
    ensure_stripe_customer,
)
from promotions.models import PromotedSlot

logger = logging.getLogger(__name__)


def _parse_int(value, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be an integer.")


def _parse_iso_date(value: str | None, field_name: str) -> date:
    if not value:
        raise ValueError(f"{field_name} is required.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid ISO date (YYYY-MM-DD).") from exc


def _promotion_price_per_day() -> int:
    cents = getattr(settings, "PROMOTION_PRICE_CENTS", 0)
    if cents <= 0:
        raise StripeConfigurationError("Promotion price is not configured.")
    return cents


def _combine_date(value: date) -> datetime:
    current_tz = timezone.get_current_timezone()
    combined = datetime.combine(value, time.min)
    return timezone.make_aware(combined, current_tz)


def _calculate_totals(duration_days: int) -> tuple[int, int, int, int]:
    price_per_day_cents = _promotion_price_per_day()
    base_cents = price_per_day_cents * duration_days
    gst_cents = int(
        (Decimal(base_cents) * Decimal("0.05")).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    total_cents = base_cents + gst_cents
    return price_per_day_cents, base_cents, gst_cents, total_cents


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def promotion_pricing(request):
    listing_id_raw = request.query_params.get("listing_id")
    if not listing_id_raw:
        return Response({"detail": "listing_id is required."}, status=status.HTTP_400_BAD_REQUEST)
    try:
        listing_id = int(listing_id_raw)
    except (TypeError, ValueError):
        return Response(
            {"detail": "listing_id must be an integer."}, status=status.HTTP_400_BAD_REQUEST
        )

    listing = get_object_or_404(Listing, pk=listing_id)
    if listing.owner_id != request.user.id:
        return Response(
            {"detail": "Only the listing owner can view promotion pricing."},
            status=status.HTTP_403_FORBIDDEN,
        )

    try:
        price_per_day = _promotion_price_per_day()
    except StripeConfigurationError:
        return Response(
            {"detail": "Promotion price is not configured."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    return Response({"price_per_day_cents": price_per_day})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pay_for_promotion(request):
    """Charge the owner for a promotion and activate the slot."""
    data = request.data or {}
    pay_with_earnings = bool(data.get("pay_with_earnings") or data.get("use_earnings_balance"))
    try:
        listing_id = _parse_int(data.get("listing_id"), "listing_id")
        start_date = _parse_iso_date(data.get("promotion_start"), "promotion_start")
        end_date = _parse_iso_date(data.get("promotion_end"), "promotion_end")
        base_price_cents = _parse_int(data.get("base_price_cents"), "base_price_cents")
        gst_cents_payload = _parse_int(data.get("gst_cents"), "gst_cents")
    except ValueError as exc:
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    if end_date < start_date:
        return Response(
            {"detail": "promotion_end must be on or after promotion_start."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    listing = get_object_or_404(Listing.objects.select_related("owner"), pk=listing_id)
    if listing.owner_id != request.user.id:
        return Response(
            {"detail": "You can only promote listings that you own."},
            status=status.HTTP_403_FORBIDDEN,
        )

    duration_days = (end_date - start_date).days + 1
    try:
        (
            price_per_day_cents,
            expected_base_cents,
            expected_gst_cents,
            total_price_cents,
        ) = _calculate_totals(duration_days)
    except StripeConfigurationError:
        logger.exception(
            "Promotion price misconfigured",
            extra={"user_id": request.user.id, "listing_id": listing.id},
        )
        return Response(
            {"detail": "Promotions are not configured right now; please try again later."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if base_price_cents != expected_base_cents or gst_cents_payload != expected_gst_cents:
        return Response(
            {
                "detail": "Promotion pricing changed, please refresh and try again.",
                "base_price_cents": expected_base_cents,
                "gst_cents": expected_gst_cents,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    starts_at = _combine_date(start_date)
    ends_at = starts_at + timedelta(days=duration_days)

    if pay_with_earnings:
        return _pay_for_promotion_with_earnings(
            request=request,
            listing=listing,
            starts_at=starts_at,
            ends_at=ends_at,
            duration_days=duration_days,
            price_per_day_cents=price_per_day_cents,
            base_cents=expected_base_cents,
            gst_cents=expected_gst_cents,
            total_price_cents=total_price_cents,
        )

    return _pay_for_promotion_with_card(
        request=request,
        listing=listing,
        starts_at=starts_at,
        ends_at=ends_at,
        duration_days=duration_days,
        price_per_day_cents=price_per_day_cents,
        base_cents=expected_base_cents,
        gst_cents=expected_gst_cents,
        total_price_cents=total_price_cents,
    )


def _pay_for_promotion_with_card(
    *,
    request,
    listing,
    starts_at,
    ends_at,
    duration_days: int,
    price_per_day_cents: int,
    base_cents: int,
    gst_cents: int,
    total_price_cents: int,
):
    data = request.data or {}
    payment_method_id = (data.get("stripe_payment_method_id") or "").strip()
    provided_customer_id = (data.get("stripe_customer_id") or "").strip()
    if not payment_method_id:
        return Response(
            {"detail": "stripe_payment_method_id is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        customer_id = ensure_stripe_customer(
            request.user,
            customer_id=provided_customer_id or None,
        )
    except StripeTransientError:
        return Response(
            {"detail": "Temporary payment issue, please retry."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except StripePaymentError as exc:
        message = str(exc) or "Payment could not be completed."
        return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
    except StripeConfigurationError:
        logger.exception(
            "Stripe configuration error creating promotion customer",
            extra={"user_id": request.user.id, "listing_id": listing.id},
        )
        return Response(
            {"detail": "Stripe is not configured; please try again later."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    try:
        payment_intent_id = charge_promotion_payment(
            owner=request.user,
            amount_cents=total_price_cents,
            payment_method_id=payment_method_id,
            customer_id=customer_id,
            metadata={
                "listing_id": str(listing.id),
                "promotion_start": starts_at.isoformat(),
                "promotion_end": ends_at.isoformat(),
                "duration_days": str(duration_days),
                "base_price_cents": str(base_cents),
                "gst_cents": str(gst_cents),
                "total_price_cents": str(total_price_cents),
            },
        )
    except StripeTransientError:
        return Response(
            {"detail": "Temporary payment issue, please retry."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    except StripePaymentError as exc:
        message = str(exc) or "Payment could not be completed."
        return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
    except StripeConfigurationError:
        logger.exception(
            "Stripe configuration error charging promotion",
            extra={"user_id": request.user.id, "listing_id": listing.id},
        )
        return Response(
            {"detail": "Stripe is not configured; please try again later."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    slot = PromotedSlot.objects.create(
        listing=listing,
        owner=request.user,
        price_per_day_cents=price_per_day_cents,
        base_price_cents=base_cents,
        gst_cents=gst_cents,
        total_price_cents=total_price_cents,
        starts_at=starts_at,
        ends_at=ends_at,
        active=True,
        stripe_session_id=payment_intent_id,
    )

    try:
        log_transaction(
            user=request.user,
            promotion_slot=slot,
            kind=Transaction.Kind.PROMOTION_CHARGE,
            amount=(Decimal(total_price_cents) / Decimal("100")).quantize(Decimal("0.01")),
            currency="cad",
            stripe_id=payment_intent_id,
        )
    except Exception:
        logger.exception(
            "Could not log promotion transaction",
            extra={"user_id": request.user.id, "slot_id": slot.id},
        )

    try:
        notification_tasks.send_promotion_payment_receipt_email.delay(
            request.user.id,
            slot.id,
        )
    except Exception:
        logger.info(
            "notifications: could not queue send_promotion_payment_receipt_email",
            exc_info=True,
        )

    return _slot_response(slot, duration_days)


def _pay_for_promotion_with_earnings(
    *,
    request,
    listing,
    starts_at,
    ends_at,
    duration_days: int,
    price_per_day_cents: int,
    base_cents: int,
    gst_cents: int,
    total_price_cents: int,
):
    total_amount = (Decimal(total_price_cents) / Decimal("100")).quantize(Decimal("0.01"))
    available = compute_owner_available_balance(request.user)
    if available < total_amount:
        return Response(
            {
                "detail": "Not enough earnings to pay for this promotion.",
                "available_earnings": f"{available.quantize(Decimal('0.01'))}",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    slot = PromotedSlot.objects.create(
        listing=listing,
        owner=request.user,
        price_per_day_cents=price_per_day_cents,
        base_price_cents=base_cents,
        gst_cents=gst_cents,
        total_price_cents=total_price_cents,
        starts_at=starts_at,
        ends_at=ends_at,
        active=True,
        stripe_session_id="",
    )
    synthetic_id = f"earnings:{slot.id}"

    try:
        log_transaction(
            user=request.user,
            promotion_slot=slot,
            booking=None,
            kind=Transaction.Kind.PROMOTION_CHARGE,
            amount=total_amount,
            currency="cad",
            stripe_id=slot.stripe_session_id or synthetic_id,
        )
        log_transaction(
            user=request.user,
            promotion_slot=slot,
            booking=None,
            kind=Transaction.Kind.OWNER_EARNING,
            amount=-total_amount,
            currency="cad",
            stripe_id=f"promo_earnings_{slot.id}",
        )
    except Exception:
        logger.exception(
            "Could not log promotion transaction",
            extra={"user_id": request.user.id, "slot_id": slot.id},
        )

    try:
        notification_tasks.send_promotion_payment_receipt_email.delay(
            request.user.id,
            slot.id,
        )
    except Exception:
        logger.info(
            "notifications: could not queue send_promotion_payment_receipt_email",
            exc_info=True,
        )

    return _slot_response(slot, duration_days)


def _slot_response(slot: PromotedSlot, duration_days: int) -> Response:
    return Response(
        {
            "slot": {
                "id": slot.id,
                "listing_id": slot.listing_id,
                "starts_at": slot.starts_at.isoformat(),
                "ends_at": slot.ends_at.isoformat(),
                "price_per_day_cents": slot.price_per_day_cents,
                "base_price_cents": slot.base_price_cents,
                "gst_cents": slot.gst_cents,
                "total_price_cents": slot.total_price_cents,
                "duration_days": duration_days,
            }
        },
        status=status.HTTP_201_CREATED,
    )
