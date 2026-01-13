import logging

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import CharField, Exists, OuterRef, Prefetch
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from listings.models import Listing, ListingPhoto
from operator_core.audit import audit
from operator_core.models import OperatorAuditEvent, OperatorNote, OperatorTag
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_listings.filters import OperatorListingFilter
from operator_listings.serializers import (
    OperatorListingDetailSerializer,
    OperatorListingListSerializer,
)

logger = logging.getLogger(__name__)

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


class OperatorListingListView(generics.ListAPIView):
    serializer_class = OperatorListingListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorListingFilter
    http_method_names = ["get"]

    def get_queryset(self):
        content_type = ContentType.objects.get_for_model(Listing)
        needs_review_qs = OperatorNote.objects.filter(
            content_type=content_type,
            object_id=Cast(OuterRef("pk"), output_field=CharField()),
            tags__name="needs_review",
        )
        return (
            Listing.objects.filter(is_deleted=False)
            .select_related("owner", "owner__payout_account", "category")
            .prefetch_related(
                Prefetch(
                    "photos",
                    queryset=ListingPhoto.objects.order_by("created_at", "id"),
                    to_attr="prefetched_photos",
                )
            )
            .annotate(needs_review=Exists(needs_review_qs))
            .order_by("-created_at")
        )


class OperatorListingDetailView(generics.RetrieveAPIView):
    serializer_class = OperatorListingDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    lookup_field = "pk"
    http_method_names = ["get"]

    def get_queryset(self):
        photos_qs = ListingPhoto.objects.all().order_by("created_at", "id")
        content_type = ContentType.objects.get_for_model(Listing)
        needs_review_qs = OperatorNote.objects.filter(
            content_type=content_type,
            object_id=Cast(OuterRef("pk"), output_field=CharField()),
            tags__name="needs_review",
        )
        return (
            Listing.objects.filter(is_deleted=False)
            .select_related("owner", "owner__payout_account", "category")
            .prefetch_related(
                Prefetch("photos", queryset=photos_qs, to_attr="prefetched_photos"),
            )
            .annotate(needs_review=Exists(needs_review_qs))
        )


def _request_ip_and_ua(request):
    ip = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip() or request.META.get(
        "REMOTE_ADDR", ""
    )
    user_agent = request.META.get("HTTP_USER_AGENT", "")
    return ip, user_agent


class OperatorListingActionBase(APIView):
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]

    def _get_listing(self, pk: int) -> Listing:
        return get_object_or_404(Listing.objects.filter(is_deleted=False), pk=pk)

    def _require_reason(self, payload) -> str | None:
        reason = (payload.get("reason") or "").strip()
        return reason or None

    def _audit_listing(
        self, request, listing: Listing, *, action: str, reason: str, before=None, after=None
    ):
        ip, ua = _request_ip_and_ua(request)
        audit(
            actor=request.user,
            action=action,
            entity_type=OperatorAuditEvent.EntityType.LISTING,
            entity_id=str(listing.id),
            reason=reason,
            before=before,
            after=after,
            meta=None,
            ip=ip,
            user_agent=ua,
        )


class OperatorListingDeactivateView(OperatorListingActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        listing = self._get_listing(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        before = {"is_active": listing.is_active}
        if listing.is_active:
            listing.is_active = False
            listing.save(update_fields=["is_active"])
        after = {"is_active": listing.is_active}

        self._audit_listing(
            request,
            listing,
            action="operator.listing.deactivate",
            reason=reason,
            before=before,
            after=after,
        )
        return Response({"ok": True, "id": listing.id, "is_active": listing.is_active})


class OperatorListingActivateView(OperatorListingActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        listing = self._get_listing(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        before = {"is_active": listing.is_active}
        if not listing.is_active:
            listing.is_active = True
            listing.save(update_fields=["is_active"])
        after = {"is_active": listing.is_active}

        self._audit_listing(
            request,
            listing,
            action="operator.listing.activate",
            reason=reason,
            before=before,
            after=after,
        )
        return Response({"ok": True, "id": listing.id, "is_active": listing.is_active})


class OperatorListingMarkNeedsReviewView(OperatorListingActionBase):
    http_method_names = ["post"]

    def post(self, request, pk: int):
        listing = self._get_listing(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        text = (payload.get("text") or "").strip()
        if not text:
            return Response({"detail": "text is required"}, status=status.HTTP_400_BAD_REQUEST)

        note = OperatorNote.objects.create(content_object=listing, author=request.user, text=text)
        tag, _ = OperatorTag.objects.get_or_create(name="needs_review")
        note.tags.add(tag)

        self._audit_listing(
            request,
            listing,
            action="operator.listing.mark_needs_review",
            reason=reason,
            before=None,
            after={"note_id": note.id, "tags": ["needs_review"], "text": text},
        )
        return Response({"ok": True, "id": listing.id, "note_id": note.id})


class OperatorListingEmergencyEditView(OperatorListingActionBase):
    http_method_names = ["patch"]

    def patch(self, request, pk: int):
        listing = self._get_listing(pk)
        payload = request.data if isinstance(request.data, dict) else {}
        reason = self._require_reason(payload)
        if not reason:
            return Response({"detail": "reason is required"}, status=status.HTTP_400_BAD_REQUEST)

        allowed_fields = {"title", "description"}
        unexpected_fields = set(payload.keys()) - allowed_fields - {"reason"}
        if unexpected_fields:
            return Response(
                {"detail": "Only title and description may be updated"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates = {}
        for field in allowed_fields:
            if field in payload:
                value = payload.get(field)
                if value is not None:
                    updates[field] = str(value).strip()

        before = {}
        after = {}
        for field, value in updates.items():
            current_value = getattr(listing, field, "")
            if value != current_value:
                before[field] = current_value
                after[field] = value
                setattr(listing, field, value)

        if not after:
            return Response(
                {"detail": "No changes to apply; provide title and/or description"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            listing.save(update_fields=list(after.keys()))
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            logger.warning(
                "Validation error during operator listing edit",
                extra={"listing_id": listing.id, "operator_id": request.user.id},
                exc_info=True,
            )
            return Response({"detail": "Invalid listing data."}, status=status.HTTP_400_BAD_REQUEST)

        self._audit_listing(
            request,
            listing,
            action="operator.listing.emergency_edit",
            reason=reason,
            before=before,
            after=after,
        )
        return Response({"ok": True, "id": listing.id, "updated_fields": list(after.keys())})
