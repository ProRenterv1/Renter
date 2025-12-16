import csv
import io
from decimal import Decimal

from django.db.models import Prefetch
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_finance.filters import OperatorTransactionFilter
from operator_finance.serializers import (
    OperatorBookingFinanceSerializer,
    OperatorTransactionSerializer,
    _format_money,
)
from payments.models import Transaction

FINANCE_ROLES = ("operator_finance", "operator_admin")


def _format_datetime(value):
    if value is None:
        return ""
    return value.isoformat()


def _csv_download(filename: str, headers: list[str], rows: list[dict]) -> HttpResponse:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=headers)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class OperatorTransactionListView(generics.ListAPIView):
    serializer_class = OperatorTransactionSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorTransactionFilter
    http_method_names = ["get"]

    def get_queryset(self):
        return Transaction.objects.select_related("user", "booking", "booking__listing").all()


class OperatorBookingFinanceView(generics.RetrieveAPIView):
    serializer_class = OperatorBookingFinanceSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    lookup_field = "pk"
    http_method_names = ["get"]

    def get_queryset(self):
        txn_qs = Transaction.objects.select_related("user", "booking", "booking__listing").order_by(
            "-created_at"
        )
        return Booking.objects.select_related("listing", "owner", "renter").prefetch_related(
            Prefetch("transactions", queryset=txn_qs)
        )


class OperatorBookingRefundView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        booking = get_object_or_404(Booking, pk=pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = (payload.get("reason") or "").strip()
        note = reason or "operator_refund"
        return Response({"ok": True, "booking_id": booking.id, "action": "refund", "reason": note})


class OperatorBookingDepositCaptureView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        booking = get_object_or_404(Booking, pk=pk)
        payload = request.data if isinstance(request.data, dict) else {}
        amount_raw = payload.get("amount")
        amount = None
        if amount_raw not in (None, ""):
            try:
                amount = Decimal(str(amount_raw))
            except Exception:
                amount = None
        return Response(
            {
                "ok": True,
                "booking_id": booking.id,
                "action": "deposit_capture",
                "amount": f"{amount:.2f}" if amount is not None else None,
            }
        )


class OperatorBookingDepositReleaseView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["post"]

    def post(self, request, pk: int):
        booking = get_object_or_404(Booking, pk=pk)
        return Response({"ok": True, "booking_id": booking.id, "action": "deposit_release"})


class OperatorPlatformRevenueExportView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["get"]

    def get(self, request):
        qs = Transaction.objects.filter(kind=Transaction.Kind.PLATFORM_FEE).select_related(
            "booking"
        )
        headers = [
            "id",
            "created_at",
            "kind",
            "amount",
            "currency",
            "booking_id",
            "stripe_id",
            "user_id",
        ]
        rows = []
        for tx in qs:
            rows.append(
                {
                    "id": tx.id,
                    "created_at": _format_datetime(tx.created_at),
                    "kind": tx.kind,
                    "amount": _format_money(tx.amount),
                    "currency": (tx.currency or "").upper(),
                    "booking_id": getattr(tx.booking, "id", None),
                    "stripe_id": tx.stripe_id or "",
                    "user_id": tx.user_id,
                }
            )
        return _csv_download("platform-revenue.csv", headers, rows)


class OperatorOwnerLedgerExportView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(FINANCE_ROLES)]
    http_method_names = ["get"]

    def get(self, request):
        owner_id = request.query_params.get("owner_id")
        owner_filter = {}
        if owner_id:
            owner_filter["user_id"] = owner_id
        earning_kinds = [
            Transaction.Kind.OWNER_EARNING,
            Transaction.Kind.REFUND,
            Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
            Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
        ]
        qs = Transaction.objects.filter(kind__in=earning_kinds, **owner_filter).select_related(
            "booking"
        )
        headers = [
            "id",
            "created_at",
            "kind",
            "amount",
            "currency",
            "booking_id",
            "stripe_id",
            "user_id",
        ]
        rows = []
        for tx in qs:
            rows.append(
                {
                    "id": tx.id,
                    "created_at": _format_datetime(tx.created_at),
                    "kind": tx.kind,
                    "amount": _format_money(tx.amount),
                    "currency": (tx.currency or "").upper(),
                    "booking_id": getattr(tx.booking, "id", None),
                    "stripe_id": tx.stripe_id or "",
                    "user_id": tx.user_id,
                }
            )
        return _csv_download("owner-ledger.csv", headers, rows)
