from __future__ import annotations

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import serializers

from disputes.models import DisputeCase, DisputeEvidence, DisputeMessage
from storage.s3 import public_url

STATUS_TO_STAGE = {
    DisputeCase.Status.OPEN: "intake",
    DisputeCase.Status.INTAKE_MISSING_EVIDENCE: "intake",
    DisputeCase.Status.AWAITING_REBUTTAL: "awaiting_rebuttal",
    DisputeCase.Status.UNDER_REVIEW: "under_review",
    DisputeCase.Status.RESOLVED_RENTER: "resolved",
    DisputeCase.Status.RESOLVED_OWNER: "resolved",
    DisputeCase.Status.RESOLVED_PARTIAL: "resolved",
    DisputeCase.Status.CLOSED_AUTO: "resolved",
}


class OperatorDisputeMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DisputeMessage
        fields = ["id", "dispute", "author", "role", "text", "created_at"]
        read_only_fields = fields


class OperatorDisputeEvidenceSerializer(serializers.ModelSerializer):
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


class OperatorDisputeListSerializer(serializers.ModelSerializer):
    booking_id = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    listing_id = serializers.SerializerMethodField()
    opened_by = serializers.CharField(source="opened_by_role", read_only=True)
    opened_by_id = serializers.IntegerField(source="opened_by.id", read_only=True)
    opened_by_label = serializers.SerializerMethodField()
    flow = serializers.SerializerMethodField()
    stage = serializers.SerializerMethodField()
    evidence_due_at = serializers.DateTimeField(source="intake_evidence_due_at", read_only=True)
    evidence_missing = serializers.SerializerMethodField()
    rebuttal_overdue = serializers.SerializerMethodField()
    flags = serializers.SerializerMethodField()
    safety_flag = serializers.SerializerMethodField()
    suspend_flag = serializers.SerializerMethodField()
    owner_email = serializers.SerializerMethodField()
    renter_email = serializers.SerializerMethodField()
    booking_summary = serializers.SerializerMethodField()
    listing_summary = serializers.SerializerMethodField()
    owner_summary = serializers.SerializerMethodField()
    renter_summary = serializers.SerializerMethodField()

    class Meta:
        model = DisputeCase
        fields = [
            "id",
            "booking_id",
            "booking",
            "listing_title",
            "listing_id",
            "opened_by",
            "opened_by_id",
            "opened_by_label",
            "opened_by_role",
            "damage_flow_kind",
            "flow",
            "category",
            "description",
            "stage",
            "status",
            "damage_assessment_category",
            "is_safety_incident",
            "requires_listing_suspend",
            "refund_amount_cents",
            "deposit_capture_amount_cents",
            "filed_at",
            "rebuttal_due_at",
            "rebuttal_overdue",
            "auto_rebuttal_timeout",
            "review_started_at",
            "resolved_at",
            "deposit_locked",
            "intake_evidence_due_at",
            "evidence_due_at",
            "evidence_missing",
            "decision_notes",
            "created_at",
            "updated_at",
            "flags",
            "safety_flag",
            "suspend_flag",
            "owner_email",
            "renter_email",
            "booking_summary",
            "listing_summary",
            "owner_summary",
            "renter_summary",
        ]
        read_only_fields = fields

    def _user_summary(self, user):
        if not user:
            return None
        name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
        if not name:
            name = getattr(user, "username", None) or f"user-{getattr(user, 'pk', '')}"
        return {
            "id": getattr(user, "pk", None),
            "name": name,
            "avatar_url": getattr(user, "avatar_url", ""),
            "identity_verified": getattr(user, "identity_verified", False),
        }

    def _primary_photo_url(self, booking) -> str | None:
        listing = getattr(booking, "listing", None)
        if not listing:
            return None
        primary = getattr(listing, "primary_photo_url", None)
        if primary:
            return primary
        photos = getattr(listing, "photos", None)
        if not photos:
            return None
        try:
            first = photos.first()
        except Exception:
            first = None
        return getattr(first, "url", None)

    def get_booking_id(self, obj: DisputeCase) -> int | None:
        booking = getattr(obj, "booking", None)
        return getattr(booking, "id", None)

    def get_listing_title(self, obj: DisputeCase) -> str | None:
        booking = getattr(obj, "booking", None)
        listing = getattr(booking, "listing", None) if booking else None
        if not listing:
            return None
        return getattr(listing, "title", None)

    def get_listing_id(self, obj: DisputeCase) -> int | None:
        booking = getattr(obj, "booking", None)
        listing = getattr(booking, "listing", None) if booking else None
        return getattr(listing, "id", None)

    def get_owner_email(self, obj: DisputeCase) -> str | None:
        booking = getattr(obj, "booking", None)
        owner = getattr(booking, "owner", None) if booking else None
        return getattr(owner, "email", None)

    def get_renter_email(self, obj: DisputeCase) -> str | None:
        booking = getattr(obj, "booking", None)
        renter = getattr(booking, "renter", None) if booking else None
        return getattr(renter, "email", None)

    def get_opened_by_label(self, obj: DisputeCase) -> str | None:
        user = getattr(obj, "opened_by", None)
        email = getattr(user, "email", None)
        if email:
            return email
        username = getattr(user, "username", None)
        if username:
            return username
        role = getattr(obj, "opened_by_role", None)
        if role == DisputeCase.OpenedByRole.OWNER:
            return self.get_owner_email(obj)
        if role == DisputeCase.OpenedByRole.RENTER:
            return self.get_renter_email(obj)
        return None

    def get_flow(self, obj: DisputeCase) -> str:
        return getattr(obj, "damage_flow_kind", "") or ""

    def get_stage(self, obj: DisputeCase) -> str:
        status = getattr(obj, "status", "") or ""
        return STATUS_TO_STAGE.get(status, status or "unknown")

    def get_evidence_missing(self, obj: DisputeCase) -> bool:
        return getattr(obj, "status", None) == DisputeCase.Status.INTAKE_MISSING_EVIDENCE

    def get_rebuttal_overdue(self, obj: DisputeCase) -> bool:
        if getattr(obj, "status", None) != DisputeCase.Status.AWAITING_REBUTTAL:
            return False
        due_at = getattr(obj, "rebuttal_due_at", None)
        return bool(due_at and due_at < timezone.now())

    def get_safety_flag(self, obj: DisputeCase) -> bool:
        return bool(getattr(obj, "is_safety_incident", False))

    def get_suspend_flag(self, obj: DisputeCase) -> bool:
        return bool(getattr(obj, "requires_listing_suspend", False))

    def get_flags(self, obj: DisputeCase) -> list[str]:
        flags: list[str] = []
        if self.get_safety_flag(obj):
            flags.append("safety")
        if self.get_suspend_flag(obj):
            flags.append("suspend")
        return flags

    def get_booking_summary(self, obj: DisputeCase) -> dict | None:
        booking = getattr(obj, "booking", None)
        if not booking:
            return None
        totals = getattr(booking, "totals", None) or {}
        return {
            "id": booking.id,
            "status": booking.status,
            "start_date": getattr(booking, "start_date", None),
            "end_date": getattr(booking, "end_date", None),
            "dispute_window_expires_at": getattr(booking, "dispute_window_expires_at", None),
            "deposit_hold_id": getattr(booking, "deposit_hold_id", ""),
            "deposit_locked": getattr(booking, "deposit_locked", False),
            "totals": totals,
        }

    def get_listing_summary(self, obj: DisputeCase) -> dict | None:
        booking = getattr(obj, "booking", None)
        listing = getattr(booking, "listing", None) if booking else None
        if not listing:
            return None
        return {
            "id": getattr(listing, "id", None),
            "title": getattr(listing, "title", ""),
            "primary_photo_url": self._primary_photo_url(booking),
        }

    def get_owner_summary(self, obj: DisputeCase) -> dict | None:
        booking = getattr(obj, "booking", None)
        owner = getattr(booking, "owner", None) if booking else None
        return self._user_summary(owner)

    def get_renter_summary(self, obj: DisputeCase) -> dict | None:
        booking = getattr(obj, "booking", None)
        renter = getattr(booking, "renter", None) if booking else None
        return self._user_summary(renter)


class OperatorDisputeDetailSerializer(OperatorDisputeListSerializer):
    messages = OperatorDisputeMessageSerializer(many=True, read_only=True)
    evidence = OperatorDisputeEvidenceSerializer(many=True, read_only=True)

    class Meta(OperatorDisputeListSerializer.Meta):
        fields = OperatorDisputeListSerializer.Meta.fields + ["messages", "evidence"]
        read_only_fields = fields

    @staticmethod
    def prefetches():
        return [
            Prefetch("messages"),
            Prefetch("evidence"),
        ]
