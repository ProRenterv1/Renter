"""Database models for rental bookings."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from listings.models import Listing


class Booking(models.Model):
    """Represents a booking request/reservation for a listing."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "requested"
        CONFIRMED = "confirmed", "confirmed"
        CANCELED = "canceled", "canceled"
        COMPLETED = "completed", "completed"

    listing = models.ForeignKey(
        Listing,
        related_name="bookings",
        on_delete=models.CASCADE,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="bookings_as_owner",
        on_delete=models.CASCADE,
    )
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="bookings_as_renter",
        on_delete=models.CASCADE,
    )
    start_date = models.DateField()
    end_date = models.DateField(help_text="End date (checkout), must be after start_date.")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.REQUESTED,
    )
    deposit_hold_id = models.CharField(max_length=120, blank=True, default="")
    totals = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["listing", "start_date", "end_date"]),
            models.Index(fields=["renter", "status"]),
            models.Index(fields=["owner", "status"]),
        ]

    def __str__(self) -> str:
        """Return a human-readable representation."""
        return f"Booking #{self.pk} for {self.listing_id} ({self.status})"

    @property
    def days(self) -> int:
        """Return the count of booked days."""
        if not self.start_date or not self.end_date:
            return 0
        return (self.end_date - self.start_date).days

    def is_active(self) -> bool:
        """Return True if the booking is pending or confirmed."""
        return self.status in {
            self.Status.REQUESTED,
            self.Status.CONFIRMED,
        }

    def is_terminal(self) -> bool:
        """Return True if the booking reached a terminal state."""
        return self.status in {
            self.Status.CANCELED,
            self.Status.COMPLETED,
        }

    def starts_in_past(self) -> bool:
        """Return True when the booking starts before today."""
        if not self.start_date:
            return False
        return self.start_date < timezone.localdate()
