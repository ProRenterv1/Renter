"""Models for handling dispute cases and related artifacts."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class DisputeCase(models.Model):
    """Represents a dispute opened for a booking."""

    class OpenedByRole(models.TextChoices):
        RENTER = "renter", "renter"
        OWNER = "owner", "owner"

    class DamageFlowKind(models.TextChoices):
        GENERIC = "generic", "generic"
        BROKE_DURING_USE = "broke_during_use", "broke_during_use"

    class Category(models.TextChoices):
        DAMAGE = "damage", "damage"
        MISSING_ITEM = "missing_item", "missing_item"
        NOT_AS_DESCRIBED = "not_as_described", "not_as_described"
        LATE_RETURN = "late_return", "late_return"
        INCORRECT_CHARGES = "incorrect_charges", "incorrect_charges"
        PICKUP_NO_SHOW = "pickup_no_show", "pickup_no_show"
        SAFETY_OR_FRAUD = "safety_or_fraud", "safety_or_fraud"

    class Status(models.TextChoices):
        OPEN = "open", "open"
        INTAKE_MISSING_EVIDENCE = "intake_missing_evidence", "intake_missing_evidence"
        AWAITING_REBUTTAL = "awaiting_rebuttal", "awaiting_rebuttal"
        UNDER_REVIEW = "under_review", "under_review"
        RESOLVED_RENTER = "resolved_renter", "resolved_renter"
        RESOLVED_OWNER = "resolved_owner", "resolved_owner"
        RESOLVED_PARTIAL = "resolved_partial", "resolved_partial"
        CLOSED_AUTO = "closed_auto", "closed_auto"

    class DamageAssessmentCategory(models.TextChoices):
        INTERNAL = "A_internal", "A_internal"
        EXTERNAL = "B_external", "B_external"
        SAFETY = "C_safety", "C_safety"
        UNKNOWN = "unknown", "unknown"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="dispute_cases",
    )
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="disputes_opened",
    )
    opened_by_role = models.CharField(
        choices=OpenedByRole.choices,
        max_length=16,
    )
    damage_flow_kind = models.CharField(
        choices=DamageFlowKind.choices,
        max_length=32,
        default=DamageFlowKind.GENERIC,
    )
    category = models.CharField(
        choices=Category.choices,
        max_length=32,
    )
    description = models.TextField()
    status = models.CharField(
        choices=Status.choices,
        max_length=32,
        default=Status.OPEN,
    )
    damage_assessment_category = models.CharField(
        choices=DamageAssessmentCategory.choices,
        max_length=16,
        null=True,
        blank=True,
    )
    is_safety_incident = models.BooleanField(default=False)
    requires_listing_suspend = models.BooleanField(default=False)
    refund_amount_cents = models.PositiveIntegerField(null=True, blank=True)
    deposit_capture_amount_cents = models.PositiveIntegerField(null=True, blank=True)
    filed_at = models.DateTimeField(default=timezone.now)
    rebuttal_due_at = models.DateTimeField(null=True, blank=True)
    auto_rebuttal_timeout = models.BooleanField(
        default=False,
        help_text="True when the rebuttal window expired without a response.",
    )
    review_started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    deposit_locked = models.BooleanField(
        default=False,
        help_text="Mirror flag to block deposit auto-release while this dispute is active.",
    )
    intake_evidence_due_at = models.DateTimeField(null=True, blank=True)
    rebuttal_12h_reminder_sent_at = models.DateTimeField(null=True, blank=True)
    decision_notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["booking", "status"]),
            models.Index(fields=["opened_by"]),
        ]

    def __str__(self) -> str:
        """Return a readable identifier."""
        return f"DisputeCase #{self.pk} booking {self.booking_id} ({self.status})"


class DisputeMessage(models.Model):
    """Conversation messages attached to a dispute case."""

    class Role(models.TextChoices):
        RENTER = "renter", "renter"
        OWNER = "owner", "owner"
        ADMIN = "admin", "admin"
        SYSTEM = "system", "system"

    dispute = models.ForeignKey(
        DisputeCase,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dispute_messages",
    )
    role = models.CharField(
        choices=Role.choices,
        max_length=16,
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class DisputeEvidence(models.Model):
    """Evidence uploads for disputes."""

    class Kind(models.TextChoices):
        PHOTO = "photo", "photo"
        VIDEO = "video", "video"
        OTHER = "other", "other"

    class AVStatus(models.TextChoices):
        PENDING = "pending", "pending"
        CLEAN = "clean", "clean"
        INFECTED = "infected", "infected"
        FAILED = "failed", "failed"

    dispute = models.ForeignKey(
        DisputeCase,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="dispute_evidence",
    )
    kind = models.CharField(
        choices=Kind.choices,
        max_length=16,
    )
    s3_key = models.CharField(max_length=512)
    filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.BigIntegerField(null=True, blank=True)
    etag = models.CharField(max_length=64, blank=True)
    av_status = models.CharField(
        choices=AVStatus.choices,
        max_length=16,
        default=AVStatus.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
