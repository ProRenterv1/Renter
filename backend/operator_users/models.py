from django.conf import settings
from django.db import models


class UserRiskFlag(models.Model):
    class Level(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "med", "Medium"
        HIGH = "high", "High"

    class Category(models.TextChoices):
        FRAUD = "fraud", "Fraud"
        ABUSE = "abuse", "Abuse"
        CHARGEBACK = "chargeback", "Chargeback"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="risk_flags",
    )
    level = models.CharField(max_length=8, choices=Level.choices)
    category = models.CharField(max_length=16, choices=Category.choices)
    note = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="risk_flags_created",
    )
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "active"]),
            models.Index(fields=["category", "active"]),
            models.Index(fields=["created_at"]),
        ]
