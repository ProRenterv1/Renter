from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response

from listings.models import Listing
from operator_core.api_base import OperatorAPIView, OperatorThrottleMixin
from operator_core.audit import audit
from operator_core.models import OperatorAuditEvent
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_promotions.filters import OperatorPromotionFilter
from operator_promotions.serializers import OperatorPromotionSerializer
from operator_users.api import ALLOWED_OPERATOR_ROLES
from promotions.models import PromotedSlot


class OperatorPromotionListView(OperatorThrottleMixin, generics.ListAPIView):
    serializer_class = OperatorPromotionSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorPromotionFilter
    http_method_names = ["get"]

    def get_queryset(self):
        return PromotedSlot.objects.select_related("listing", "owner").order_by("-created_at")


class OperatorPromotionActionBase(OperatorAPIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]

    def _require_reason(self, payload):
        reason = (payload.get("reason") or "").strip() if isinstance(payload, dict) else ""
        return reason or None

    def _request_ip_and_ua(self, request):
        ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[
            0
        ].strip() or request.META.get("REMOTE_ADDR", "")
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        return ip, user_agent

    def _audit(
        self, *, request, entity_id: str, action: str, reason: str, before, after, meta=None
    ):
        ip, ua = self._request_ip_and_ua(request)
        audit(
            actor=request.user,
            action=action,
            entity_type=OperatorAuditEvent.EntityType.LISTING,
            entity_id=str(entity_id),
            reason=reason,
            before=before,
            after=after,
            meta=meta,
            ip=ip,
            user_agent=ua,
        )


class OperatorPromotionGrantCompedView(OperatorPromotionActionBase):
    http_method_names = ["post"]

    def post(self, request):
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        listing_id = payload.get("listing_id")
        try:
            listing_id_int = int(listing_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "listing_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST
            )

        listing = get_object_or_404(Listing.objects.select_related("owner"), pk=listing_id_int)

        starts_at_raw = payload.get("starts_at")
        ends_at_raw = payload.get("ends_at")
        starts_at = parse_datetime(starts_at_raw) if isinstance(starts_at_raw, str) else None
        ends_at = parse_datetime(ends_at_raw) if isinstance(ends_at_raw, str) else None
        if not starts_at or not ends_at:
            return Response(
                {"detail": "starts_at and ends_at are required ISO datetimes"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if timezone.is_naive(starts_at):
            starts_at = timezone.make_aware(starts_at, timezone.get_current_timezone())
        if timezone.is_naive(ends_at):
            ends_at = timezone.make_aware(ends_at, timezone.get_current_timezone())
        if ends_at < starts_at:
            return Response(
                {"detail": "ends_at must be on/after starts_at"}, status=status.HTTP_400_BAD_REQUEST
            )

        before = None
        slot = PromotedSlot.objects.create(
            listing=listing,
            owner=listing.owner,
            price_per_day_cents=0,
            base_price_cents=0,
            gst_cents=0,
            total_price_cents=0,
            starts_at=starts_at,
            ends_at=ends_at,
            active=True,
            stripe_session_id="comped",
        )

        note = (payload.get("note") or "").strip()
        after = {
            "slot_id": slot.id,
            "listing_id": listing.id,
            "owner_id": listing.owner_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "active": slot.active,
            "note": note,
        }

        self._audit(
            request=request,
            entity_id=listing.id,
            action="operator.promo.grant_comped",
            reason=reason,
            before=before,
            after=after,
            meta={"note": note},
        )

        serializer = OperatorPromotionSerializer(slot)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class OperatorPromotionCancelEarlyView(OperatorPromotionActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        slot = get_object_or_404(PromotedSlot.objects.select_related("listing", "owner"), pk=pk)
        before = {
            "starts_at": slot.starts_at.isoformat() if slot.starts_at else None,
            "ends_at": slot.ends_at.isoformat() if slot.ends_at else None,
            "active": slot.active,
        }

        now = timezone.now()
        if slot.ends_at and slot.ends_at > now:
            slot.ends_at = now
        slot.active = False
        slot.save(update_fields=["ends_at", "active", "updated_at"])

        note = (payload.get("note") or "").strip()
        after = {
            "starts_at": slot.starts_at.isoformat() if slot.starts_at else None,
            "ends_at": slot.ends_at.isoformat() if slot.ends_at else None,
            "active": slot.active,
            "note": note,
        }

        self._audit(
            request=request,
            entity_id=slot.listing_id,
            action="operator.promo.cancel_early",
            reason=reason,
            before=before,
            after=after,
            meta={"note": note, "promotion_id": slot.id},
        )

        serializer = OperatorPromotionSerializer(slot)
        return Response(serializer.data, status=status.HTTP_200_OK)
