from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models


class OperatorAuditEvent(models.Model):
    class EntityType(models.TextChoices):
        USER = "user", "User"
        LISTING = "listing", "Listing"
        BOOKING = "booking", "Booking"
        DISPUTE_CASE = "dispute_case", "Dispute Case"
        DISPUTE_MESSAGE = "dispute_message", "Dispute Message"
        DISPUTE_EVIDENCE = "dispute_evidence", "Dispute Evidence"
        OPERATOR_NOTE = "operator_note", "Operator Note"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_audit_events",
    )
    action = models.CharField(max_length=128)
    entity_type = models.CharField(max_length=64, choices=EntityType.choices)
    entity_id = models.CharField(max_length=64)
    reason = models.TextField()
    before_json = models.JSONField(null=True, blank=True)
    after_json = models.JSONField(null=True, blank=True)
    meta_json = models.JSONField(null=True, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["entity_type", "entity_id", "created_at"]),
            models.Index(fields=["actor", "created_at"]),
        ]
        ordering = ["-created_at"]


class OperatorTag(models.Model):
    name = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return self.name


class OperatorNote(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.CharField(max_length=64)
    content_object = GenericForeignKey("content_type", "object_id")

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_notes_authored",
    )
    text = models.TextField()
    tags = models.ManyToManyField(OperatorTag, blank=True, related_name="notes")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["created_at"])]
