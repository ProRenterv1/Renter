"""API endpoints for disputes."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from bookings.models import Booking
from storage.s3 import booking_object_key, guess_content_type, presign_put
from storage.tasks import scan_and_finalize_dispute_evidence

from .models import DisputeCase, DisputeEvidence, DisputeMessage


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

    class Meta:
        model = DisputeMessage
        fields = ["id", "dispute", "author", "role", "text", "created_at"]
        read_only_fields = ["id", "dispute", "author", "role", "created_at"]


class DisputeEvidenceSerializer(serializers.ModelSerializer):
    """Serialize dispute evidence uploads (read-only for now)."""

    class Meta:
        model = DisputeEvidence
        fields = [
            "id",
            "dispute",
            "uploaded_by",
            "kind",
            "s3_key",
            "filename",
            "content_type",
            "size",
            "etag",
            "av_status",
            "created_at",
        ]
        read_only_fields = fields


class DisputeCaseSerializer(serializers.ModelSerializer):
    """Serialize dispute cases with nested messages/evidence."""

    messages = DisputeMessageSerializer(many=True, read_only=True)
    evidence = DisputeEvidenceSerializer(many=True, read_only=True)

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
            "review_started_at",
            "resolved_at",
            "deposit_locked",
            "decision_notes",
            "messages",
            "evidence",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "opened_by",
            "opened_by_role",
            "status",
            "filed_at",
            "deposit_locked",
            "created_at",
            "updated_at",
        ]

    def validate_booking(self, booking: Booking) -> Booking:
        user = self.context["request"].user
        if user.is_staff:
            return booking
        if booking.owner_id == user.id or booking.renter_id == user.id:
            return booking
        raise serializers.ValidationError("You are not allowed to file disputes for this booking.")

    def create(self, validated_data: dict[str, Any]) -> DisputeCase:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        booking: Booking = validated_data["booking"]

        has_deposit_hold = bool(getattr(booking, "deposit_hold_id", ""))
        opened_by_role = DisputeCase.OpenedByRole.RENTER
        if booking.owner_id == getattr(user, "id", None):
            opened_by_role = DisputeCase.OpenedByRole.OWNER
        elif booking.renter_id == getattr(user, "id", None):
            opened_by_role = DisputeCase.OpenedByRole.RENTER

        dispute = DisputeCase.objects.create(
            **validated_data,
            opened_by=user,
            opened_by_role=opened_by_role,
            status=DisputeCase.Status.OPEN,
            filed_at=timezone.now(),
            deposit_locked=has_deposit_hold,
        )

        updated_fields: list[str] = []
        if not booking.is_disputed:
            booking.is_disputed = True
            updated_fields.append("is_disputed")
        if has_deposit_hold and not booking.deposit_locked:
            booking.deposit_locked = True
            updated_fields.append("deposit_locked")
        if updated_fields:
            updated_fields.append("updated_at")
            booking.save(update_fields=updated_fields)

        return dispute


class DisputeCaseViewSet(viewsets.ModelViewSet):
    """CRUD for dispute cases and related messages."""

    serializer_class = DisputeCaseSerializer
    permission_classes = [IsDisputeParticipant]

    def get_queryset(self):
        qs = DisputeCase.objects.select_related("booking", "opened_by")
        user = self.request.user
        if user and user.is_staff:
            return qs
        return qs.filter(models.Q(booking__owner_id=user.id) | models.Q(booking__renter_id=user.id))

    def get_object(self):
        obj = (
            DisputeCase.objects.select_related("booking", "opened_by")
            .prefetch_related("messages", "evidence")
            .get(pk=self.kwargs["pk"])
        )
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer: DisputeCaseSerializer) -> None:
        serializer.save(opened_by=self.request.user)

    @action(detail=True, methods=["post"], url_path="messages")
    def create_message(self, request, *args, **kwargs):
        dispute: DisputeCase = self.get_object()
        booking = dispute.booking
        user = request.user

        if user.is_staff:
            role = DisputeMessage.Role.ADMIN
        elif booking and booking.renter_id == user.id:
            role = DisputeMessage.Role.RENTER
        elif booking and booking.owner_id == user.id:
            role = DisputeMessage.Role.OWNER
        else:
            role = DisputeMessage.Role.SYSTEM

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

        max_bytes = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
        if max_bytes and size_hint > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
        max_bytes = getattr(settings, "S3_MAX_UPLOAD_BYTES", None)
        if max_bytes and size_int > max_bytes:
            return Response(
                {"detail": f"File too large. Max allowed is {max_bytes} bytes."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = request.data.get("filename") or "upload"
        content_type = request.data.get("content_type") or guess_content_type(filename)
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
        evidence.av_status = DisputeEvidence.AVStatus.PENDING
        evidence.save()

        meta = {
            "etag": etag,
            "filename": filename,
            "content_type": content_type,
            "size": size_int,
        }
        scan_and_finalize_dispute_evidence.delay(
            key=key,
            dispute_id=dispute.id,
            uploaded_by_id=user.id,
            meta=meta,
        )

        return Response({"status": "queued", "key": key}, status=status.HTTP_202_ACCEPTED)
