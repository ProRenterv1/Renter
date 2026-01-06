from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Iterable

from django.db.models import Count
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from bookings.models import Booking
from disputes.models import DisputeCase
from listings.models import Listing
from operator_core.permissions import HasOperatorRole, IsOperator
from users.models import User


class OperatorDashboardSerializer(serializers.Serializer):
    today = serializers.DictField()
    last_7d = serializers.DictField()
    risk = serializers.DictField()
    risk_items = serializers.DictField()
    open_disputes_count = serializers.IntegerField()
    rebuttals_due_soon_count = serializers.IntegerField()


ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


def _display_name(user) -> str:
    if not user:
        return ""
    name = (user.get_full_name() or "").strip()
    if name:
        return name
    for attr in ("username", "email"):
        value = (getattr(user, attr, "") or "").strip()
        if value:
            return value
    if getattr(user, "id", None):
        return f"User {user.id}"
    return ""


def _total_charge_label(booking: Booking) -> str:
    totals = booking.totals if isinstance(booking.totals, dict) else {}
    raw = totals.get("total_charge") or totals.get("rental_subtotal") or ""
    if raw is None:
        return ""
    return str(raw)


def _gmv_from_totals_dict(totals: dict | None) -> Decimal:
    """
    Best-effort GMV extraction that tolerates missing/partial totals.
    """
    if not totals or not isinstance(totals, dict):
        return Decimal("0")

    def _to_decimal(value) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal("0")

    if "total_charge" in totals:
        return _to_decimal(totals.get("total_charge"))

    subtotal = _to_decimal(totals.get("rental_subtotal"))
    renter_fee = _to_decimal(totals.get("renter_fee"))
    damage_deposit = _to_decimal(totals.get("damage_deposit"))
    if subtotal or renter_fee or damage_deposit:
        return subtotal + renter_fee + damage_deposit
    return Decimal("0")


def _sum_gmv_for_bookings(bookings: Iterable[dict]) -> Decimal:
    total = Decimal("0")
    for totals in bookings:
        total += _gmv_from_totals_dict(totals)
    return total


class OperatorDashboardView(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]

    def get(self, request):
        now = timezone.now()
        today = timezone.localdate()
        seven_days_ago = now - timedelta(days=7)

        users_today = User.objects.filter(date_joined__date=today).count()
        users_last_7 = User.objects.filter(date_joined__gte=seven_days_ago).count()

        listings_today = Listing.objects.filter(created_at__date=today).count()
        listings_last_7 = Listing.objects.filter(created_at__gte=seven_days_ago).count()

        bookings_today = Booking.objects.filter(created_at__date=today)
        bookings_last_7 = Booking.objects.filter(created_at__gte=seven_days_ago)

        def _booking_stats(qs):
            status_counts = dict(
                qs.values("status").annotate(c=Count("id")).values_list("status", "c")
            )
            gmv_qs = qs.filter(status__in=[Booking.Status.PAID, Booking.Status.COMPLETED])
            totals_list = gmv_qs.values_list("totals", flat=True)
            gmv = _sum_gmv_for_bookings(totals_list)
            return status_counts, gmv

        today_status_counts, today_gmv = _booking_stats(bookings_today)
        last7_status_counts, last7_gmv = _booking_stats(bookings_last_7)

        overdue_qs = Booking.objects.filter(
            end_date__lt=today,
            return_confirmed_at__isnull=True,
            status__in=[Booking.Status.CONFIRMED, Booking.Status.PAID],
        )
        overdue_bookings_count = overdue_qs.count()
        disputed_bookings_count = Booking.objects.filter(is_disputed=True).count()

        open_statuses = [
            DisputeCase.Status.OPEN,
            DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            DisputeCase.Status.AWAITING_REBUTTAL,
            DisputeCase.Status.UNDER_REVIEW,
        ]
        open_disputes_qs = DisputeCase.objects.filter(status__in=open_statuses)
        open_disputes_count = open_disputes_qs.count()
        rebuttals_due_soon_count = DisputeCase.objects.filter(
            status=DisputeCase.Status.AWAITING_REBUTTAL,
            rebuttal_due_at__lte=now + timedelta(hours=12),
            rebuttal_due_at__gte=now,
        ).count()

        failed_payments_qs = Booking.objects.filter(
            status=Booking.Status.CONFIRMED,
            charge_payment_intent_id="",
        )
        failed_payments_count = failed_payments_qs.count()

        overdue_items = []
        for booking in overdue_qs.select_related("listing", "renter").order_by("end_date")[:5]:
            end_date = booking.end_date
            overdue_days = (today - end_date).days if end_date else 0
            listing_title = getattr(booking.listing, "title", None) if booking.listing_id else None
            overdue_items.append(
                {
                    "booking_id": booking.id,
                    "listing_id": booking.listing_id,
                    "listing_title": listing_title,
                    "renter_name": _display_name(booking.renter),
                    "renter_email": getattr(booking.renter, "email", None),
                    "end_date": end_date.isoformat() if end_date else None,
                    "overdue_days": max(overdue_days, 0),
                }
            )

        disputed_items = []
        for dispute in open_disputes_qs.select_related("booking").order_by("-created_at")[:5]:
            filed_at = dispute.created_at
            disputed_items.append(
                {
                    "dispute_id": dispute.id,
                    "booking_id": dispute.booking_id,
                    "filed_at": filed_at.isoformat() if filed_at else None,
                }
            )

        failed_payment_items = []
        for booking in failed_payments_qs.select_related("renter").order_by("-created_at")[:5]:
            renter = booking.renter
            failed_payment_items.append(
                {
                    "booking_id": booking.id,
                    "renter_name": _display_name(renter),
                    "renter_email": getattr(renter, "email", None),
                    "amount": _total_charge_label(booking),
                    "created_at": booking.created_at.isoformat() if booking.created_at else None,
                }
            )

        data = {
            "today": {
                "new_users": users_today,
                "new_listings": listings_today,
                "new_bookings_by_status": today_status_counts,
                "gmv_approx": today_gmv,
            },
            "last_7d": {
                "new_users": users_last_7,
                "new_listings": listings_last_7,
                "new_bookings_by_status": last7_status_counts,
                "gmv_approx": last7_gmv,
            },
            "risk": {
                "overdue_bookings_count": overdue_bookings_count,
                "disputed_bookings_count": disputed_bookings_count,
                "failed_payments_count": failed_payments_count,
            },
            "risk_items": {
                "overdue_bookings": overdue_items,
                "disputed_bookings": disputed_items,
                "failed_payments": failed_payment_items,
            },
            "open_disputes_count": open_disputes_count,
            "rebuttals_due_soon_count": rebuttals_due_soon_count,
        }

        serializer = OperatorDashboardSerializer(data)
        return Response(serializer.data)
