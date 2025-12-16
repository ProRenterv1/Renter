import logging
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from operator_bookings.filters import OperatorBookingFilter
from operator_bookings.models import BookingEvent
from operator_bookings.serializers import (
    AdjustBookingDatesSerializer,
    ForceCancelBookingSerializer,
    OperatorBookingDetailSerializer,
    OperatorBookingListSerializer,
    ResendBookingNotificationsSerializer,
)
from operator_bookings.services import (
    adjust_booking_dates,
    force_cancel_booking,
    force_complete_booking,
    resend_booking_notifications,
)
from operator_core.permissions import HasOperatorRole, IsOperator
from payments.stripe_api import StripeConfigurationError, StripePaymentError, StripeTransientError

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)

logger = logging.getLogger(__name__)


def _safe_json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe_json_value(v) for v in value]
    return value


class OperatorBookingListView(generics.ListAPIView):
    serializer_class = OperatorBookingListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorBookingFilter
    http_method_names = ["get"]

    def get_queryset(self):
        qs = (
            Booking.objects.select_related("listing", "owner", "renter")
            .filter(listing__is_deleted=False)
            .order_by("-created_at")
        )
        # Default to excluding overdue bookings unless explicitly requested via ?overdue=...
        if "overdue" not in self.request.query_params:
            today = timezone.localdate()
            qs = qs.exclude(end_date__lt=today, return_confirmed_at__isnull=True)
        return qs


class OperatorBookingDetailView(generics.RetrieveAPIView):
    serializer_class = OperatorBookingDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    lookup_field = "pk"
    http_method_names = ["get"]

    def get_queryset(self):
        events_qs = BookingEvent.objects.select_related("actor").order_by("-created_at", "-id")
        return (
            Booking.objects.select_related("listing", "owner", "renter")
            .filter(listing__is_deleted=False)
            .prefetch_related(
                Prefetch("events", queryset=events_qs, to_attr="prefetched_events"),
                Prefetch("dispute_cases", to_attr="prefetched_disputes"),
            )
        )


def _request_ip_and_ua(request):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip, user_agent


class OperatorBookingActionBase(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["post"]

    def _get_booking(self, pk: int) -> Booking:
        return get_object_or_404(
            Booking.objects.select_related("listing", "owner", "renter").filter(
                listing__is_deleted=False
            ),
            pk=pk,
        )

    def _audit(self, request, *, booking: Booking, action: str, reason: str, before, after):
        from operator_core.audit import audit
        from operator_core.models import OperatorAuditEvent

        ip, ua = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action=action,
            entity_type=OperatorAuditEvent.EntityType.BOOKING,
            entity_id=str(booking.id),
            reason=reason,
            before=_safe_json_value(before),
            after=_safe_json_value(after),
            meta=None,
            ip=ip,
            user_agent=ua,
        )


class OperatorBookingForceCancelView(OperatorBookingActionBase):
    def post(self, request, pk: int):
        booking = self._get_booking(pk)
        serializer = ForceCancelBookingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = serializer.validated_data["actor"]
        cancel_reason = serializer.validated_data.get("reason") or None
        audit_reason = cancel_reason or "operator.force_cancel"

        before = {
            "status": booking.status,
            "canceled_by": booking.canceled_by,
            "canceled_reason": booking.canceled_reason,
        }
        try:
            booking = force_cancel_booking(
                booking, actor=actor, reason=cancel_reason, operator_user=request.user
            )
        except StripeTransientError:
            return Response(
                {"detail": "Temporary payment issue while refunding; please retry."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except StripePaymentError as exc:
            message = str(exc) or "Unable to process refund for this cancellation."
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)
        except StripeConfigurationError:
            logger.exception(
                "Stripe configuration error while operator canceling booking %s", booking.id
            )
            return Response(
                {"detail": "Payment processor is not configured; please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc) or "Unable to cancel booking."
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        after = {
            "status": booking.status,
            "canceled_by": booking.canceled_by,
            "canceled_reason": booking.canceled_reason,
        }
        self._audit(
            request,
            booking=booking,
            action="operator.booking.force_cancel",
            reason=audit_reason,
            before=before,
            after=after,
        )

        return Response(
            {"ok": True, "booking_id": booking.id, "status": booking.status},
            status=status.HTTP_200_OK,
        )


class OperatorBookingForceCompleteView(OperatorBookingActionBase):
    def post(self, request, pk: int):
        booking = self._get_booking(pk)
        reason = ""
        if isinstance(request.data, dict):
            reason = (request.data.get("reason") or "").strip()
        reason_text = reason or "operator.force_complete"

        before = {
            "status": booking.status,
            "return_confirmed_at": booking.return_confirmed_at,
            "dispute_window_expires_at": booking.dispute_window_expires_at,
        }
        try:
            booking = force_complete_booking(booking, operator_user=request.user)
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc) or "Unable to complete booking."
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        after = {
            "status": booking.status,
            "return_confirmed_at": booking.return_confirmed_at,
            "dispute_window_expires_at": booking.dispute_window_expires_at,
        }
        self._audit(
            request,
            booking=booking,
            action="operator.booking.force_complete",
            reason=reason_text,
            before=before,
            after=after,
        )

        return Response(
            {
                "ok": True,
                "booking_id": booking.id,
                "status": booking.status,
                "dispute_window_expires_at": booking.dispute_window_expires_at,
            },
            status=status.HTTP_200_OK,
        )


class OperatorBookingAdjustDatesView(OperatorBookingActionBase):
    def post(self, request, pk: int):
        booking = self._get_booking(pk)
        serializer = AdjustBookingDatesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        start_date: date = serializer.validated_data["start_date"]
        end_date: date = serializer.validated_data["end_date"]
        reason = serializer.validated_data.get("reason") or "operator.adjust_dates"

        before = {
            "start_date": booking.start_date,
            "end_date": booking.end_date,
            "totals": booking.totals or {},
        }
        try:
            booking = adjust_booking_dates(
                booking, start_date=start_date, end_date=end_date, operator_user=request.user
            )
        except ValidationError as exc:
            return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)

        after = {
            "start_date": booking.start_date,
            "end_date": booking.end_date,
            "totals": booking.totals or {},
        }
        self._audit(
            request,
            booking=booking,
            action="operator.booking.adjust_dates",
            reason=reason,
            before=before,
            after=after,
        )

        return Response(
            {
                "ok": True,
                "booking_id": booking.id,
                "status": booking.status,
                "start_date": booking.start_date,
                "end_date": booking.end_date,
                "totals": booking.totals or {},
            }
        )


class OperatorBookingResendNotificationsView(OperatorBookingActionBase):
    def post(self, request, pk: int):
        booking = self._get_booking(pk)
        serializer = ResendBookingNotificationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        types = serializer.validated_data["types"]
        reason = serializer.validated_data.get("reason") or "operator.resend_notifications"

        before = {"types_requested": types}
        queued, failed = resend_booking_notifications(
            booking, types=types, operator_user=request.user
        )
        after = {"queued": queued, "failed": failed}

        self._audit(
            request,
            booking=booking,
            action="operator.booking.resend_notifications",
            reason=reason,
            before=before,
            after=after,
        )

        status_code = status.HTTP_200_OK if not failed else status.HTTP_207_MULTI_STATUS
        return Response(
            {
                "ok": True,
                "booking_id": booking.id,
                "status": booking.status,
                "queued": queued,
                "failed": failed or None,
            },
            status=status_code,
        )
