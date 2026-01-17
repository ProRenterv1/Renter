"""API endpoints for disputes."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from bookings.models import Booking
from core.redis import push_event
from core.settings_resolver import get_bool, get_int
from listings.models import ListingPhoto
from notifications import tasks as notification_tasks
from storage.s3 import booking_object_key, guess_content_type, presign_put, public_url
from storage.tasks import scan_and_finalize_dispute_evidence
from storage.validators import coerce_int, max_bytes_for_content_type, validate_image_limits

from .intake import update_dispute_intake_status
from .models import DisputeCase, DisputeEvidence, DisputeMessage
from .tasks import start_rebuttal_window

logger = logging.getLogger(__name__)

User = get_user_model()


def _dispute_evidence_limit() -> int:
    configured = coerce_int(getattr(settings, "DISPUTE_MAX_EVIDENCE_FILES", None)) or 0
    return get_int("DISPUTE_MAX_EVIDENCE_FILES", configured)


_DISPUTE_WRITE_LOCKED_STATUSES = {
    DisputeCase.Status.RESOLVED_RENTER,
    DisputeCase.Status.RESOLVED_OWNER,
    DisputeCase.Status.RESOLVED_PARTIAL,
    DisputeCase.Status.CLOSED_AUTO,
}


def _dispute_writes_locked(dispute: DisputeCase) -> bool:
    return dispute.status in _DISPUTE_WRITE_LOCKED_STATUSES


def _finalize_booking_flags(booking: Booking, dispute_id: int) -> None:
    active_statuses = {
        DisputeCase.Status.OPEN,
        DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
        DisputeCase.Status.AWAITING_REBUTTAL,
        DisputeCase.Status.UNDER_REVIEW,
    }
    other_active = (
        DisputeCase.objects.filter(booking=booking, status__in=active_statuses)
        .exclude(pk=dispute_id)
        .exists()
    )
    if other_active:
        return
    booking.is_disputed = False
    booking.deposit_locked = False
    booking.save(update_fields=["is_disputed", "deposit_locked", "updated_at"])


class IsDisputeParticipant(permissions.BasePermission):
    """Allow booking participants or staff to access a dispute."""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(user and user.is_authenticated)

    def has_object_permission(self, request, view, obj: DisputeCase) -> bool:
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff:
            return True
        booking = getattr(obj, "booking", None)
        if not booking:
            return False
        return booking.owner_id == user.id or booking.renter_id == user.id


class DisputeMessageSerializer(serializers.ModelSerializer):
    """Serialize dispute conversation messages."""

    text = serializers.CharField(max_length=4000)

    class Meta:
        model = DisputeMessage
        fields = ["id", "dispute", "author", "role", "text", "created_at"]
        read_only_fields = ["id", "dispute", "author", "role", "created_at"]


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    """Serialize dispute evidence uploads (read-only for now)."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = DisputeEvidence
        fields = [
            "id",
            "dispute",
            "uploaded_by",
            "kind",
            "s3_key",
            "url",
            "filename",
            "content_type",
            "size",
            "etag",
            "av_status",
            "created_at",
        ]
        read_only_fields = fields

    def get_url(self, obj: DisputeEvidence) -> str | None:
        if not getattr(obj, "s3_key", ""):
            return None
        return public_url(obj.s3_key)


class DisputeCaseSerializer(serializers.ModelSerializer):
    """Serialize dispute cases with nested messages/evidence."""

    messages = DisputeMessageSerializer(many=True, read_only=True)
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)
    booking_start_date = serializers.DateField(source="booking.start_date", read_only=True)
    booking_end_date = serializers.DateField(source="booking.end_date", read_only=True)
    listing_title = serializers.CharField(
        source="booking.listing.title", read_only=True, allow_blank=True
    )
    listing_primary_photo_url = serializers.SerializerMethodField()
    owner_summary = serializers.SerializerMethodField()
    renter_summary = serializers.SerializerMethodField()

    class Meta:
        model = DisputeCase
        fields = [
            "id",
            "booking",
            "opened_by",
            "opened_by_role",
            "damage_flow_kind",
            "category",
            "description",
            "status",
            "damage_assessment_category",
            "is_safety_incident",
            "requires_listing_suspend",
            "refund_amount_cents",
            "deposit_capture_amount_cents",
            "filed_at",
            "rebuttal_due_at",
            "auto_rebuttal_timeout",
            "review_started_at",
            "resolved_at",
            "deposit_locked",
            "decision_notes",
            "messages",
            "evidence",
            "created_at",
            "updated_at",
            "booking_start_date",
            "booking_end_date",
            "listing_title",
            "listing_primary_photo_url",
            "owner_summary",
            "renter_summary",
        ]
        read_only_fields = [
            "id",
            "opened_by",
            "opened_by_role",
            "status",
            "filed_at",
            "rebuttal_due_at",
            "auto_rebuttal_timeout",
            "deposit_locked",
            "created_at",
            "updated_at",
        ]

    def get_listing_primary_photo_url(self, obj: DisputeCase) -> str | None:
        booking = getattr(obj, "booking", None)
        listing = getattr(booking, "listing", None) if booking else None
        if not listing:
            return None
        primary = getattr(listing, "primary_photo_url", None)
        if primary:
            return primary
        photos = getattr(listing, "photos", None)
        try:
            first = photos.first()
        except Exception:
            first = None
        return getattr(first, "url", None)

    def _user_summary(self, user) -> dict | None:
        if not user:
            return None
        full_name = (user.get_full_name() or "").strip()
        if not full_name:
            full_name = user.username or f"user-{user.pk}"
        return {
            "id": user.pk,
            "name": full_name,
            "avatar_url": getattr(user, "avatar_url", ""),
            "identity_verified": getattr(user, "identity_verified", False),
            "rating": getattr(user, "rating", None),
        }

    def get_owner_summary(self, obj: DisputeCase) -> dict | None:
        booking = getattr(obj, "booking", None)
        owner = getattr(booking, "owner", None) if booking else None
        return self._user_summary(owner)

    def get_renter_summary(self, obj: DisputeCase) -> dict | None:
        booking = getattr(obj, "booking", None)
        renter = getattr(booking, "renter", None) if booking else None
        return self._user_summary(renter)

    def validate_booking(self, booking: Booking) -> Booking:
        user = self.context["request"].user
        if user.is_staff:
            return booking
        if booking.owner_id == user.id or booking.renter_id == user.id:
            return booking
        raise serializers.ValidationError("You are not allowed to file disputes for this booking.")

    def create(self, validated_data: dict[str, Any]) -> DisputeCase:
        request = self.context.get("request")
        user = validated_data.pop("opened_by", getattr(request, "user", None))
        booking: Booking = validated_data["booking"]
        damage_flow_kind = validated_data.get(
            "damage_flow_kind", DisputeCase.DamageFlowKind.GENERIC
        )
        active_statuses = {
            DisputeCase.Status.OPEN,
            DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            DisputeCase.Status.AWAITING_REBUTTAL,
            DisputeCase.Status.UNDER_REVIEW,
        }
        if DisputeCase.objects.filter(booking=booking, status__in=active_statuses).exists():
            raise serializers.ValidationError(
                {"booking": ["An active dispute already exists for this booking."]}
            )

        if not user or not getattr(user, "is_authenticated", False):
            raise serializers.ValidationError({"non_field_errors": ["Authentication required."]})

        if getattr(user, "is_staff", False):
            opened_by_role = DisputeCase.OpenedByRole.OWNER
        elif booking.owner_id == getattr(user, "id", None):
            opened_by_role = DisputeCase.OpenedByRole.OWNER
        elif booking.renter_id == getattr(user, "id", None):
            opened_by_role = DisputeCase.OpenedByRole.RENTER
        else:
            raise serializers.ValidationError(
                {"non_field_errors": ["You are not allowed to file disputes for this booking."]}
            )

        if (
            opened_by_role == DisputeCase.OpenedByRole.RENTER
            and damage_flow_kind == DisputeCase.DamageFlowKind.BROKE_DURING_USE
        ):
            validated_data["category"] = DisputeCase.Category.DAMAGE
        elif damage_flow_kind == DisputeCase.DamageFlowKind.BROKE_DURING_USE:
            validated_data["damage_flow_kind"] = DisputeCase.DamageFlowKind.GENERIC

        category = validated_data.get("category")
        is_pickup_no_show = category == DisputeCase.Category.PICKUP_NO_SHOW
        is_safety_fraud = category == DisputeCase.Category.SAFETY_OR_FRAUD
        allow_late_safety_fraud = get_bool("DISPUTE_ALLOW_LATE_SAFETY_FRAUD", True)
        safety_fraud_exempt = is_safety_fraud and allow_late_safety_fraud
        now = timezone.now()
        auto_close = False
        expires_at = booking.dispute_window_expires_at
        if not user.is_staff:
            if booking.status not in {Booking.Status.PAID, Booking.Status.COMPLETED}:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Disputes can only be filed for paid or recently completed bookings."
                        ]
                    }
                )

            window_expired = bool(expires_at and now > expires_at)
            if window_expired and not safety_fraud_exempt and not booking.deposit_hold_id:
                raise serializers.ValidationError(
                    {"non_field_errors": ["Dispute window expired for this booking."]}
                )

        if is_pickup_no_show:
            if booking.status != Booking.Status.PAID:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Pickup no-show disputes can only be filed for paid bookings."
                        ]
                    }
                )
            if booking.pickup_confirmed_at:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Pickup no-show disputes must be filed before pickup is confirmed."
                        ]
                    }
                )

        window_expired = bool(expires_at and now > expires_at)
        if window_expired and not safety_fraud_exempt and not user.is_staff:
            auto_close = True

        has_deposit_hold = bool(getattr(booking, "deposit_hold_id", ""))
        created_at = now
        status_value = DisputeCase.Status.CLOSED_AUTO if auto_close else DisputeCase.Status.OPEN
        rebuttal_due_at = None
        if not auto_close and is_pickup_no_show:
            no_show_hours = max(get_int("DISPUTE_NO_SHOW_REBUTTAL_HOURS", 2), 1)
            status_value = DisputeCase.Status.AWAITING_REBUTTAL
            rebuttal_due_at = created_at + timedelta(hours=no_show_hours)
        dispute = DisputeCase.objects.create(
            **validated_data,
            opened_by=user,
            opened_by_role=opened_by_role,
            status=status_value,
            filed_at=created_at,
            resolved_at=created_at if auto_close else None,
            deposit_locked=False if auto_close else has_deposit_hold,
            rebuttal_due_at=rebuttal_due_at,
        )

        updated_fields: list[str] = []
        if not auto_close and not booking.is_disputed:
            booking.is_disputed = True
            updated_fields.append("is_disputed")
        if not auto_close and has_deposit_hold and not booking.deposit_locked:
            booking.deposit_locked = True
            updated_fields.append("deposit_locked")
        if updated_fields:
            updated_fields.append("updated_at")
            booking.save(update_fields=updated_fields)

        if not auto_close:
            if is_pickup_no_show:
                payload = {
                    "dispute_id": dispute.id,
                    "booking_id": booking.id,
                    "status": dispute.status,
                }
                for user_id in (booking.owner_id, booking.renter_id):
                    try:
                        push_event(user_id, "dispute:opened", payload)
                    except Exception:
                        logger.info(
                            "dispute create: failed to push dispute:opened event",
                            extra={"user_id": user_id, "dispute_id": dispute.id},
                            exc_info=True,
                        )
                transaction.on_commit(lambda: start_rebuttal_window.delay(dispute.id))
            else:
                update_dispute_intake_status(dispute.id)

        try:
            BookingEvent = apps.get_model("operator_bookings", "BookingEvent")
            BookingEvent.objects.create(
                booking=booking,
                actor=user if getattr(user, "is_authenticated", False) else None,
                type=BookingEvent.Type.DISPUTE_OPENED,
                payload={
                    "dispute_id": dispute.id,
                    "category": dispute.category,
                    "auto_closed": auto_close,
                },
            )
        except Exception:
            logger.exception(
                "booking_event: failed to create dispute_opened event",
                extra={
                    "booking_id": booking.id,
                    "dispute_id": dispute.id,
                    "auto_closed": auto_close,
                },
            )

        return dispute


class DisputeCaseViewSet(viewsets.ModelViewSet):
    """CRUD for dispute cases and related messages."""

    serializer_class = DisputeCaseSerializer
    permission_classes = [IsDisputeParticipant]

    def get_queryset(self):
        qs = DisputeCase.objects.select_related(
            "booking",
            "booking__listing",
            "booking__owner",
            "booking__renter",
            "opened_by",
        ).prefetch_related(
            Prefetch("booking__listing__photos", queryset=ListingPhoto.objects.order_by("id"))
        )
        user = self.request.user
        booking_filter = self.request.query_params.get("booking")
        if booking_filter:
            qs = qs.filter(booking_id=booking_filter)
        if user and user.is_staff:
            return qs
        return qs.filter(models.Q(booking__owner_id=user.id) | models.Q(booking__renter_id=user.id))

    def get_object(self):
        obj = (
            DisputeCase.objects.select_related(
                "booking",
                "booking__listing",
                "booking__owner",
                "booking__renter",
                "opened_by",
            )
            .prefetch_related(
                "messages",
                "evidence",
                Prefetch("booking__listing__photos", queryset=ListingPhoto.objects.order_by("id")),
            )
            .get(pk=self.kwargs["pk"])
        )
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer: DisputeCaseSerializer) -> None:
        serializer.save(opened_by=self.request.user)

    @action(detail=False, methods=["post"], url_path="evidence/validate")
    def evidence_validate(self, request, *args, **kwargs):
        booking_raw = request.data.get("booking")
        if booking_raw in (None, ""):
            return Response({"detail": "booking is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            booking_id = int(booking_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "booking must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )

        booking = Booking.objects.filter(pk=booking_id).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_staff or booking.owner_id == user.id or booking.renter_id == user.id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        files = request.data.get("files")
        if not isinstance(files, list) or not files:
            return Response(
                {"detail": "files must be a non-empty list."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_files = _dispute_evidence_limit()
        if max_files and len(files) > max_files:
            return Response(
                {"detail": f"Too many files. Max allowed is {max_files}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        errors: list[dict[str, Any]] = []
        for index, meta in enumerate(files):
            if not isinstance(meta, dict):
                errors.append({"index": index, "detail": "File metadata must be an object."})
                continue

            filename = meta.get("filename") or "upload"
            content_type_raw = meta.get("content_type")
            content_type = (
                content_type_raw
                if isinstance(content_type_raw, str) and content_type_raw
                else guess_content_type(filename)
            )
            size_raw = meta.get("size")
            if size_raw in (None, ""):
                errors.append({"index": index, "filename": filename, "detail": "size is required."})
                continue
            try:
                size_int = int(size_raw)
            except (TypeError, ValueError):
                errors.append(
                    {"index": index, "filename": filename, "detail": "size must be an integer."}
                )
                continue
            if size_int <= 0:
                errors.append(
                    {
                        "index": index,
                        "filename": filename,
                        "detail": "size must be greater than zero.",
                    }
                )
                continue

            width = coerce_int(meta.get("width"))
            height = coerce_int(meta.get("height"))
            max_bytes = max_bytes_for_content_type(content_type) or getattr(
                settings, "S3_MAX_UPLOAD_BYTES", None
            )
            if max_bytes and size_int > max_bytes:
                errors.append(
                    {
                        "index": index,
                        "filename": filename,
                        "detail": f"File too large. Max allowed is {max_bytes} bytes.",
                    }
                )
                continue
            image_error = validate_image_limits(
                content_type=content_type,
                size=size_int,
                width=width,
                height=height,
            )
            if image_error:
                errors.append({"index": index, "filename": filename, "detail": image_error})

        if errors:
            return Response(
                {"detail": "One or more files are invalid.", "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="evidence/presign")
    def evidence_presign_for_booking(self, request, *args, **kwargs):
        booking_raw = request.data.get("booking")
        if booking_raw in (None, ""):
            return Response({"detail": "booking is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            booking_id = int(booking_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "booking must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )

        booking = Booking.objects.filter(pk=booking_id).first()
        if not booking:
            return Response({"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        if not (user.is_staff or booking.owner_id == user.id or booking.renter_id == user.id):
            return Response(status=status.HTTP_403_FORBIDDEN)

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        content_md5 = request.data.get("content_md5")
        size_raw = request.data.get("size")
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_hint = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_hint <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_bytes = max_bytes_for_content_type(content_type) or getattr(
            settings, "S3_MAX_UPLOAD_BYTES", None
        )
        if max_bytes and size_hint > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image_error = validate_image_limits(
            content_type=content_type,
            size=size_hint,
            width=None,
            height=None,
        )
        if image_error:
            return Response({"detail": image_error}, status=status.HTTP_400_BAD_REQUEST)

        key = booking_object_key(
            booking_id=booking.id,
            user_id=user.id,
            filename=filename,
        )
        try:
            presigned = presign_put(
                key,
                content_type=content_type,
                content_md5=content_md5,
                size_hint=size_hint,
            )
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "key": key,
                "upload_url": presigned["upload_url"],
                "headers": presigned["headers"],
                "max_bytes": max_bytes,
                "tagging": "av-status=pending",
            }
        )

    @action(detail=True, methods=["post"], url_path="messages")
    def create_message(self, request, *args, **kwargs):
        dispute: DisputeCase = self.get_object()
        booking = dispute.booking
        user = request.user

        if booking and booking.renter_id == user.id:
            role = DisputeMessage.Role.RENTER
        elif booking and booking.owner_id == user.id:
            role = DisputeMessage.Role.OWNER
        elif user.is_staff:
            role = DisputeMessage.Role.ADMIN
        else:
            role = DisputeMessage.Role.SYSTEM

        if _dispute_writes_locked(dispute):
            return Response(
                {"detail": "Dispute is closed and cannot accept new messages."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = DisputeMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = DisputeMessage.objects.create(
            dispute=dispute,
            author=user,
            role=role,
            text=serializer.validated_data["text"],
        )
        return Response(DisputeMessageSerializer(message).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="evidence/presign")
    def evidence_presign(self, request, pk=None):
        dispute: DisputeCase = self.get_object()
        booking = dispute.booking
        user = request.user
        if not (user.is_staff or booking.owner_id == user.id or booking.renter_id == user.id):
            return Response(status=status.HTTP_403_FORBIDDEN)
        if _dispute_writes_locked(dispute):
            return Response(
                {"detail": "Dispute is closed and cannot accept new evidence."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_files = _dispute_evidence_limit()
        if max_files:
            current_count = DisputeEvidence.objects.filter(dispute=dispute).count()
            if current_count >= max_files:
                return Response(
                    {"detail": f"Too many files. Max allowed is {max_files}."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        content_md5 = request.data.get("content_md5")
        size_raw = request.data.get("size")
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_hint = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_hint <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_bytes = max_bytes_for_content_type(content_type) or getattr(
            settings, "S3_MAX_UPLOAD_BYTES", None
        )
        if max_bytes and size_hint > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image_error = validate_image_limits(
            content_type=content_type,
            size=size_hint,
            width=None,
            height=None,
        )
        if image_error:
            return Response({"detail": image_error}, status=status.HTTP_400_BAD_REQUEST)

        key = booking_object_key(
            booking_id=booking.id,
            user_id=user.id,
            filename=filename,
        )
        try:
            presigned = presign_put(
                key,
                content_type=content_type,
                content_md5=content_md5,
                size_hint=size_hint,
            )
        except ValueError:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "key": key,
                "upload_url": presigned["upload_url"],
                "headers": presigned["headers"],
                "max_bytes": max_bytes,
                "tagging": "av-status=pending",
            }
        )

    @action(detail=True, methods=["post"], url_path="evidence/complete")
    def evidence_complete(self, request, pk=None):
        dispute: DisputeCase = self.get_object()
        booking = dispute.booking
        user = request.user
        if not (user.is_staff or booking.owner_id == user.id or booking.renter_id == user.id):
            return Response(status=status.HTTP_403_FORBIDDEN)
        if _dispute_writes_locked(dispute):
            return Response(
                {"detail": "Dispute is closed and cannot accept new evidence."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        key = request.data.get("key")
        etag = request.data.get("etag")
        size_raw = request.data.get("size")
        if not key or not etag:
            return Response(
                {"detail": "key and etag required."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_raw in (None, ""):
            return Response({"detail": "size is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            size_int = int(size_raw)
        except (TypeError, ValueError):
            return Response(
                {"detail": "size must be an integer."}, status=status.HTTP_400_BAD_REQUEST
            )
        if size_int <= 0:
            return Response(
                {"detail": "size must be greater than zero."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_files = _dispute_evidence_limit()
        if max_files:
            existing = DisputeEvidence.objects.filter(
                dispute=dispute, uploaded_by=user, s3_key=key
            ).first()
            if not existing:
                current_count = DisputeEvidence.objects.filter(dispute=dispute).count()
                if current_count >= max_files:
                    return Response(
                        {"detail": f"Too many files. Max allowed is {max_files}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
        width = coerce_int(request.data.get("width"))
        height = coerce_int(request.data.get("height"))
        original_size = coerce_int(request.data.get("original_size"))
        compressed_size = coerce_int(request.data.get("compressed_size"))
        max_bytes = max_bytes_for_content_type(content_type) or getattr(
            settings, "S3_MAX_UPLOAD_BYTES", None
        )
        if max_bytes and size_int > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        image_error = validate_image_limits(
            content_type=content_type,
            size=size_int,
            width=width,
            height=height,
        )
        if image_error:
            return Response({"detail": image_error}, status=status.HTTP_400_BAD_REQUEST)

        kind = request.data.get("kind") or DisputeEvidence.Kind.PHOTO

        evidence, _ = DisputeEvidence.objects.get_or_create(
            dispute=dispute,
            uploaded_by=user,
            s3_key=key,
            defaults={"kind": kind},
        )
        evidence.kind = kind
        evidence.filename = filename
        evidence.content_type = content_type
        evidence.size = size_int
        evidence.etag = (etag or "").strip('"')
        if hasattr(evidence, "width"):
            evidence.width = width
        if hasattr(evidence, "height"):
            evidence.height = height
        evidence.av_status = DisputeEvidence.AVStatus.PENDING
        evidence.save()

        meta = {
            "etag": etag,
            "filename": filename,
            "content_type": content_type,
            "size": size_int,
            "kind": kind,
            "width": width,
            "height": height,
            "original_size": original_size,
            "compressed_size": compressed_size,
        }
        scan_and_finalize_dispute_evidence.delay(
            key=key,
            dispute_id=dispute.id,
            uploaded_by_id=user.id,
            meta=meta,
        )

        if dispute.status == DisputeCase.Status.INTAKE_MISSING_EVIDENCE:
            update_dispute_intake_status(dispute.id)

        return Response({"status": "queued", "key": key}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=["post"], url_path="close")
    def close_dispute(self, request, pk=None):
        dispute: DisputeCase = self.get_object()
        user = request.user
        if dispute.opened_by_id != user.id:
            return Response(status=status.HTTP_403_FORBIDDEN)
        if _dispute_writes_locked(dispute):
            return Response(
                {"detail": "Dispute is already closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        now = timezone.now()
        with transaction.atomic():
            locked = (
                DisputeCase.objects.select_for_update().select_related("booking").get(pk=dispute.id)
            )
            if _dispute_writes_locked(locked):
                return Response(
                    {"detail": "Dispute is already closed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            locked.status = DisputeCase.Status.CLOSED_AUTO
            locked.resolved_at = now
            role_label = (
                "renter" if locked.opened_by_role == DisputeCase.OpenedByRole.RENTER else "owner"
            )
            decision_note = f"Closed by {role_label}."
            existing_notes = (locked.decision_notes or "").strip()
            locked.decision_notes = f"{existing_notes} {decision_note}".strip()
            locked.save(update_fields=["status", "resolved_at", "decision_notes", "updated_at"])
            booking_locked = locked.booking
            if booking_locked:
                _finalize_booking_flags(booking_locked, locked.id)
            dispute = locked

        try:
            BookingEvent = apps.get_model("operator_bookings", "BookingEvent")
            BookingEvent.objects.create(
                booking=dispute.booking,
                actor=user if getattr(user, "is_authenticated", False) else None,
                type=BookingEvent.Type.OPERATOR_ACTION,
                payload={
                    "action": "dispute_closed_by_user",
                    "dispute_id": dispute.id,
                    "opened_by_role": dispute.opened_by_role,
                },
            )
        except Exception:
            logger.exception(
                "booking_event: failed to create dispute_closed_by_user event",
                extra={"booking_id": dispute.booking_id, "dispute_id": dispute.id},
            )

        try:
            notification_tasks.notify_dispute_update(dispute.id, "both")
        except Exception:
            logger.info(
                "dispute close: failed to notify update",
                extra={"dispute_id": dispute.id},
                exc_info=True,
            )

        serializer = self.get_serializer(dispute)
        return Response(serializer.data, status=status.HTTP_200_OK)
