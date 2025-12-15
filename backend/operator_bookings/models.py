from django.conf import settings
from django.db import models


class BookingEvent(models.Model):
    class Type(models.TextChoices):
        STATUS_CHANGE = "status_change", "Status change"
        EMAIL_SENT = "email_sent", "Email sent"
        EMAIL_FAILED = "email_failed", "Email failed"
        OPERATOR_ACTION = "operator_action", "Operator action"
        DISPUTE_OPENED = "dispute_opened", "Dispute opened"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="events",
    )
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operator_booking_events",
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["booking", "created_at"]),
            models.Index(fields=["type", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"BookingEvent {self.pk} for booking {self.booking_id} ({self.type})"
