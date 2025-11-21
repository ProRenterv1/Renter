"""Database models for Stripe Identity verification tracking."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class IdentityVerification(models.Model):
    """Represents a Stripe Identity verification session for a user."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="identity_verifications",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PENDING,
    )
    session_id = models.CharField(max_length=255, unique=True)
    last_error_code = models.CharField(max_length=64, blank=True, default="")
    last_error_reason = models.CharField(max_length=255, blank=True, default="")
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["session_id"]),
        ]

    @property
    def is_verified(self) -> bool:
        """Return True if the verification has completed successfully."""
        return self.status == self.Status.VERIFIED


def is_user_identity_verified(user) -> bool:
    """Return True if the user has any verified identity session."""
    if user is None or not getattr(user, "pk", None):
        return False
    return IdentityVerification.objects.filter(
        user=user, status=IdentityVerification.Status.VERIFIED
    ).exists()


def mark_session_verified(user, session_id: str) -> IdentityVerification:
    """Mark a verification session as verified for the given user."""
    verification, _ = IdentityVerification.objects.update_or_create(
        user=user,
        session_id=session_id,
        defaults={
            "status": IdentityVerification.Status.VERIFIED,
            "verified_at": timezone.now(),
            "last_error_code": "",
            "last_error_reason": "",
        },
    )
    return verification
