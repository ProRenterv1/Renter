import csv
import io
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from disputres.services import settlement
from operator_bookings.models import BookingEvent
from operator_core.audit import audit
from operator_core.models import OperatorAuditEvent
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_finance.filters import OperatorTransactionFilter
from operator_finance.renderers import CSVRenderer
from operator_finance.serializers import (
    BookingFinanceSerializer,
    OperatorTransactionSerializer,
    _format_money,
)
from payments.models import Transaction
from payments.stripe_api import (
    StripeConfigurationError,
    StripePaymentError,
    StripeTransientError,
    get_payment_intent_fee,
)

logger = logging.getLogger(__name__)

FINANCE_ROLES = ("operator_finance", "operator_admin")


def _format_datetime(value):
    if value is None:
        return ""
    return value.isoformat()


def _request_ip_and_ua(request):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip, user_agent


def _parse_amount_to_cents(value) -> int:
    """Parse a dollar amount to integer cents, raising ValueError on bad input."""
    try:
        quantized = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid amount")
    if quantized <= Decimal("0"):
        raise ValueError("Amount must be greater than zero")
    cents = int((quantized * 100).to_integral_value())
    return cents


def _safe_notify_booking_action(booking: Booking, action: str):
    """Best-effort notification hook; intentionally swallow errors."""
    try:
        from notifications import tasks as notification_tasks

        if hasattr(notification_tasks, "send_operator_booking_action"):
            notification_tasks.send_operator_booking_action.delay(  # type: ignore[attr-defined]
                booking_id=booking.id, action=action
            )
    except Exception:
        # Fire-and-forget; do not block operator actions on notification failures.
        pass


def _csv_download(filename: str, headers: list[str], rows: list[dict]) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _parse_date_param(raw: str | None):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        return None


def _date_range_to_datetimes(start_date, end_date):
    tz = timezone.get_current_timezone()
    start_dt = None
    end_dt = None
    if start_date:
        start_dt = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    if end_date:
        end_dt = timezone.make_aware(datetime.combine(end_date, time.max), tz)
    return start_dt, end_dt


def _safe_decimal(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _decimal_to_cents(value: Decimal) -> int:
    quantized = value.quantize(Decimal("0.01"))
    return int((quantized * 100).to_integral_value())


def _owner_refund_amount(booking: Booking) -> Decimal:
    totals = booking.totals or {}
    owner_payout = _safe_decimal(totals.get("owner_payout"))
    if owner_payout is None:
        rental_subtotal = _safe_decimal(totals.get("rental_subtotal"))
        owner_fee_total = _safe_decimal(totals.get("owner_fee_total") or totals.get("owner_fee"))
        if rental_subtotal is not None and owner_fee_total is not None:
            owner_payout = rental_subtotal - owner_fee_total
    if owner_payout is None:
        raise ValueError("Booking totals missing owner payout values.")
    owner_payout = owner_payout.quantize(Decimal("0.01"))
    if owner_payout <= Decimal("0"):
        raise ValueError("Booking owner payout must be greater than zero.")
    return owner_payout


def _refund_window_bounds(booking: Booking) -> tuple[datetime | None, datetime | None]:
    if not booking.paid_at or not booking.end_date:
        return None, None
    tz = timezone.get_current_timezone()
    paid_at = booking.paid_at
    if timezone.is_naive(paid_at):
        paid_at = timezone.make_aware(paid_at, tz)
    window_start = paid_at
    actual_end = booking.end_date - timedelta(days=1)
    window_end = timezone.make_aware(datetime.combine(actual_end, time.max), tz) + timedelta(
        hours=48
    )
    return window_start, window_end


def _booking_gst_amount(booking: Booking | None) -> Decimal:
    if booking is None:
        return Decimal("0.00")
    totals = booking.totals or {}
    renter_gst = _safe_decimal(totals.get("renter_fee_gst")) or Decimal("0.00")
    owner_gst = _safe_decimal(totals.get("owner_fee_gst")) or Decimal("0.00")
    return (renter_gst + owner_gst).quantize(Decimal("0.01"))


def _promotion_gst_amount(promotion_slot) -> Decimal:
    if promotion_slot is None:
        return Decimal("0.00")
    try:
        gst_cents = int(getattr(promotion_slot, "gst_cents", 0) or 0)
    except (TypeError, ValueError):
        return Decimal("0.00")
    return (Decimal(gst_cents) / Decimal("100")).quantize(Decimal("0.01"))


def _stripe_fee_for_intent_id(intent_id: str | None, cache: dict[str, Decimal | None]) -> Decimal:
    intent_id = (intent_id or "").strip()
    if not intent_id or not intent_id.startswith(("pi_", "ch_", "cs_")):
        return Decimal("0.00")
    if intent_id in cache:
        return cache[intent_id] or Decimal("0.00")
    try:
        fee_value = get_payment_intent_fee(intent_id)
    except (StripeConfigurationError, StripePaymentError, StripeTransientError) as exc:
        logger.warning(
            "platform_revenue_export: stripe fee lookup failed for intent %s: %s",
            intent_id,
            str(exc) or "stripe error",
        )
        fee_value = None
    cache[intent_id] = fee_value
    return fee_value or Decimal("0.00")


def _stripe_fee_for_booking(booking: Booking | None, cache: dict[str, Decimal | None]) -> Decimal:
    if booking is None:
        return Decimal("0.00")
    intent_id = getattr(booking, "charge_payment_intent_id", "") or ""
    return _stripe_fee_for_intent_id(intent_id, cache)


class OperatorTransactionListView(generics.ListAPIView):
    serializer_class = OperatorTransactionSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorTransactionFilter
    http_method_names = ["get"]

    def get_queryset(self):
        return Transaction.objects.select_related("user", "booking").all().order_by("-created_at")


class OperatorBookingFinanceView(generics.RetrieveAPIView):
    serializer_class = BookingFinanceSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    lookup_field = "pk"
    http_method_names = ["get"]

    def get_queryset(self):
        txn_qs = Transaction.objects.select_related("user").order_by("-created_at")
        return Booking.objects.select_related("listing", "owner", "renter").prefetch_related(
            Prefetch("transactions", queryset=txn_qs)
        )


class OperatorBookingRefundView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        booking = get_object_or_404(
            Booking.objects.select_related("listing", "owner", "renter"), pk=pk
        )
        payload = request.data if isinstance(request.data, dict) else {}
        reason = (payload.get("reason") or "").strip()
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)
        notify_user = bool(payload.get("notify_user"))

        window_start, window_end = _refund_window_bounds(booking)
        if not window_start or not window_end:
            return Response(
                {"detail": "Refunds are only allowed after payment is completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        now = timezone.now()
        if now < window_start:
            return Response(
                {"detail": "Refunds are only allowed after payment is completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if now > window_end:
            return Response(
                {"detail": "Refunds are only allowed within 48 hours after booking end."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            owner_refund_amount = _owner_refund_amount(booking)
        except ValueError:
            return Response(
                {"detail": "Unable to determine owner payout for refund."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        owner_refund_cents = _decimal_to_cents(owner_refund_amount)

        amount_cents = owner_refund_cents
        amount_raw = payload.get("amount")
        if amount_raw not in (None, ""):
            try:
                requested_cents = _parse_amount_to_cents(amount_raw)
            except ValueError:
                logger.warning(
                    "Invalid refund amount provided by operator",
                    extra={"booking_id": booking.id, "operator_id": request.user.id},
                    exc_info=True,
                )
                return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
            if requested_cents != owner_refund_cents:
                return Response(
                    {"detail": "Refund amount must match the owner payout for this booking."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        before = {
            "charge_payment_intent_id": booking.charge_payment_intent_id,
            "amount_cents": amount_cents,
        }
        try:
            refund_id, refunded_cents = settlement.refund_booking_charge(
                booking, amount_cents, dispute_id=None
            )
        except StripePaymentError:
            logger.warning(
                "Stripe payment error while operator refunding booking",
                extra={"booking_id": booking.id, "operator_id": request.user.id},
                exc_info=True,
            )
            return Response(
                {"detail": "Unable to process refund for this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        after = {
            "refund_id": refund_id,
            "refunded_cents": refunded_cents,
            "charge_payment_intent_id": booking.charge_payment_intent_id,
        }

        BookingEvent.objects.create(
            booking=booking,
            type=BookingEvent.Type.OPERATOR_ACTION,
            actor=request.user,
            payload={
                "action": "finance_refund",
                "amount_cents": refunded_cents,
                "stripe_id": refund_id or booking.charge_payment_intent_id,
            },
        )

        ip, ua = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action="operator.booking.refund",
            entity_type=OperatorAuditEvent.EntityType.BOOKING,
            entity_id=str(booking.id),
            reason=reason,
            before=before,
            after=after,
            meta=None,
            ip=ip,
            user_agent=ua,
        )

        if notify_user:
            _safe_notify_booking_action(booking, "refund")

        return Response(
            {
                "ok": True,
                "booking_id": booking.id,
                "refund_id": refund_id,
                "refunded_cents": refunded_cents,
            },
            status=status.HTTP_200_OK,
        )


class OperatorBookingDepositCaptureView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        booking = get_object_or_404(
            Booking.objects.select_related("listing", "owner", "renter"), pk=pk
        )
        payload = request.data if isinstance(request.data, dict) else {}
        reason = (payload.get("reason") or "").strip()
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)
        amount_raw = payload.get("amount")
        if amount_raw in (None, ""):
            return Response({"detail": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            amount_cents = _parse_amount_to_cents(amount_raw)
        except ValueError:
            logger.warning(
                "Invalid deposit capture amount provided by operator",
                extra={"booking_id": booking.id, "operator_id": request.user.id},
                exc_info=True,
            )
            return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)

        before = {"deposit_hold_id": booking.deposit_hold_id, "amount_cents": amount_cents}
        try:
            intent_id, captured_cents = settlement.capture_deposit_amount(
                booking, amount_cents, dispute_id=None
            )
        except StripePaymentError:
            logger.warning(
                "Stripe payment error while operator capturing deposit",
                extra={"booking_id": booking.id, "operator_id": request.user.id},
                exc_info=True,
            )
            return Response(
                {"detail": "Unable to capture deposit for this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        after = {"deposit_hold_id": intent_id, "captured_cents": captured_cents}

        BookingEvent.objects.create(
            booking=booking,
            type=BookingEvent.Type.OPERATOR_ACTION,
            actor=request.user,
            payload={
                "action": "finance_deposit_capture",
                "amount_cents": captured_cents,
                "stripe_id": intent_id,
            },
        )

        ip, ua = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action="operator.booking.deposit_capture",
            entity_type=OperatorAuditEvent.EntityType.BOOKING,
            entity_id=str(booking.id),
            reason=reason,
            before=before,
            after=after,
            meta=None,
            ip=ip,
            user_agent=ua,
        )

        _safe_notify_booking_action(booking, "deposit_capture")

        return Response(
            {
                "ok": True,
                "booking_id": booking.id,
                "payment_intent_id": intent_id,
                "captured_cents": captured_cents,
            },
            status=status.HTTP_200_OK,
        )


class OperatorBookingDepositReleaseView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        booking = get_object_or_404(
            Booking.objects.select_related("listing", "owner", "renter"), pk=pk
        )
        payload = request.data if isinstance(request.data, dict) else {}
        reason = (payload.get("reason") or "").strip()
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        before = {"deposit_hold_id": booking.deposit_hold_id}
        try:
            settlement.release_deposit_hold(booking, dispute_id=None)
        except StripePaymentError:
            logger.warning(
                "Stripe payment error while operator releasing deposit hold",
                extra={"booking_id": booking.id, "operator_id": request.user.id},
                exc_info=True,
            )
            return Response(
                {"detail": "Unable to release deposit for this booking."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        after = {"deposit_hold_id": booking.deposit_hold_id}

        BookingEvent.objects.create(
            booking=booking,
            type=BookingEvent.Type.OPERATOR_ACTION,
            actor=request.user,
            payload={"action": "finance_deposit_release", "stripe_id": booking.deposit_hold_id},
        )

        ip, ua = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action="operator.booking.deposit_release",
            entity_type=OperatorAuditEvent.EntityType.BOOKING,
            entity_id=str(booking.id),
            reason=reason,
            before=before,
            after=after,
            meta=None,
            ip=ip,
            user_agent=ua,
        )

        _safe_notify_booking_action(booking, "deposit_release")

        return Response(
            {"ok": True, "booking_id": booking.id, "deposit_hold_id": booking.deposit_hold_id},
            status=status.HTTP_200_OK,
        )


class OperatorPlatformRevenueExportView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    renderer_classes = [CSVRenderer]
    http_method_names = ["get"]

    def get(self, request):
        date_from = _parse_date_param(request.query_params.get("from"))
        date_to = _parse_date_param(request.query_params.get("to"))
        start_dt, end_dt = _date_range_to_datetimes(date_from, date_to)

        headers = [
            "created_at",
            "source",
            "booking_id",
            "txn_id",
            "Gross income",
            "Stripe Fee",
            "GST",
            "Net income",
            "currency",
        ]
        rows: list[dict] = []
        stripe_fee_cache: dict[str, Decimal | None] = {}

        txn_filter = {
            "kind__in": [Transaction.Kind.PLATFORM_FEE, Transaction.Kind.PROMOTION_CHARGE]
        }
        if start_dt:
            txn_filter["created_at__gte"] = start_dt
        if end_dt:
            txn_filter["created_at__lte"] = end_dt

        ledger_txns = (
            Transaction.objects.filter(**txn_filter)
            .select_related("booking", "promotion_slot")
            .order_by("created_at", "id")
        )
        for tx in ledger_txns:
            booking = getattr(tx, "booking", None)
            gross_income = tx.amount
            if tx.kind == Transaction.Kind.PLATFORM_FEE:
                stripe_fee = _stripe_fee_for_booking(booking, stripe_fee_cache)
                if stripe_fee == Decimal("0.00") and tx.stripe_id:
                    stripe_fee = _stripe_fee_for_intent_id(tx.stripe_id, stripe_fee_cache)
            elif tx.kind == Transaction.Kind.PROMOTION_CHARGE:
                stripe_fee = _stripe_fee_for_intent_id(tx.stripe_id, stripe_fee_cache)
            else:
                stripe_fee = Decimal("0.00")
            gst_amount = (
                _booking_gst_amount(booking)
                if booking is not None
                else _promotion_gst_amount(getattr(tx, "promotion_slot", None))
            )
            net_income = gross_income - stripe_fee - gst_amount
            rows.append(
                {
                    "created_at": _format_datetime(tx.created_at),
                    "source": tx.kind,
                    "booking_id": getattr(tx.booking, "id", None),
                    "txn_id": tx.id,
                    "Gross income": _format_money(gross_income),
                    "Stripe Fee": _format_money(stripe_fee),
                    "GST": _format_money(gst_amount),
                    "Net income": _format_money(net_income),
                    "currency": (tx.currency or "").upper(),
                }
            )

        booking_filter = {"status__in": [Booking.Status.PAID, Booking.Status.COMPLETED]}
        if date_from:
            booking_filter["created_at__date__gte"] = date_from
        if date_to:
            booking_filter["created_at__date__lte"] = date_to

        platform_fee_booking_ids = set(
            Transaction.objects.filter(kind=Transaction.Kind.PLATFORM_FEE)
            .exclude(booking_id=None)
            .values_list("booking_id", flat=True)
        )

        approx_bookings = (
            Booking.objects.filter(**booking_filter)
            .exclude(id__in=platform_fee_booking_ids)
            .only("id", "totals", "created_at", "charge_payment_intent_id")
            .order_by("created_at", "id")
        )
        for booking in approx_bookings:
            totals = booking.totals or {}
            platform_fee_total = totals.get("platform_fee_total") or totals.get("platform_fee")
            try:
                amount_decimal = Decimal(str(platform_fee_total))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if amount_decimal is None or amount_decimal <= Decimal("0"):
                continue
            stripe_fee = _stripe_fee_for_booking(booking, stripe_fee_cache)
            gst_amount = _booking_gst_amount(booking)
            net_income = amount_decimal - stripe_fee - gst_amount
            rows.append(
                {
                    "created_at": _format_datetime(getattr(booking, "created_at", None)),
                    "source": "booking_totals_approx",
                    "booking_id": booking.id,
                    "txn_id": "",
                    "Gross income": _format_money(amount_decimal),
                    "Stripe Fee": _format_money(stripe_fee),
                    "GST": _format_money(gst_amount),
                    "Net income": _format_money(net_income),
                    "currency": "CAD",
                }
            )

        return _csv_download("platform-revenue.csv", headers, rows)


class OperatorOwnerLedgerExportView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    renderer_classes = [CSVRenderer]
    http_method_names = ["get"]

    def get(self, request):
        owner_id = request.query_params.get("owner_id")
        date_from = _parse_date_param(request.query_params.get("from"))
        date_to = _parse_date_param(request.query_params.get("to"))
        start_dt, end_dt = _date_range_to_datetimes(date_from, date_to)

        txn_filter = {}
        if owner_id:
            txn_filter["user_id"] = owner_id
        if start_dt:
            txn_filter["created_at__gte"] = start_dt
        if end_dt:
            txn_filter["created_at__lte"] = end_dt

        qs = (
            Transaction.objects.filter(**txn_filter)
            .select_related("booking")
            .order_by("created_at", "id")
        )

        headers = ["created_at", "txn_id", "kind", "amount", "currency", "booking_id", "stripe_id"]
        rows = []
        for tx in qs:
            rows.append(
                {
                    "created_at": _format_datetime(tx.created_at),
                    "txn_id": tx.id,
                    "kind": tx.kind,
                    "amount": _format_money(tx.amount),
                    "currency": (tx.currency or "").upper(),
                    "booking_id": getattr(tx.booking, "id", None),
                    "stripe_id": tx.stripe_id or "",
                }
            )
        return _csv_download("owner-ledger.csv", headers, rows)
