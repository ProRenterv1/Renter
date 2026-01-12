import csv
import io
import logging
from datetime import datetime, time
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
from payments.stripe_api import StripePaymentError

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
        amount_cents = None
        amount_raw = payload.get("amount")
        if amount_raw not in (None, ""):
            try:
                amount_cents = _parse_amount_to_cents(amount_raw)
            except ValueError:
                logger.warning(
                    "Invalid refund amount provided by operator",
                    extra={"booking_id": booking.id, "operator_id": request.user.id},
                    exc_info=True,
                )
                return Response({"detail": "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)

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

        headers = ["created_at", "source", "booking_id", "txn_id", "amount", "currency"]
        rows: list[dict] = []

        txn_filter = {
            "kind__in": [Transaction.Kind.PLATFORM_FEE, Transaction.Kind.PROMOTION_CHARGE]
        }
        if start_dt:
            txn_filter["created_at__gte"] = start_dt
        if end_dt:
            txn_filter["created_at__lte"] = end_dt

        ledger_txns = (
            Transaction.objects.filter(**txn_filter)
            .select_related("booking")
            .order_by("created_at", "id")
        )
        for tx in ledger_txns:
            rows.append(
                {
                    "created_at": _format_datetime(tx.created_at),
                    "source": tx.kind,
                    "booking_id": getattr(tx.booking, "id", None),
                    "txn_id": tx.id,
                    "amount": _format_money(tx.amount),
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
            .only("id", "totals")
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
            rows.append(
                {
                    "created_at": _format_datetime(getattr(booking, "created_at", None)),
                    "source": "booking_totals_approx",
                    "booking_id": booking.id,
                    "txn_id": "",
                    "amount": _format_money(amount_decimal),
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
