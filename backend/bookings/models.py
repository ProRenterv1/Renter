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
        PAID = "paid", "paid"
        CANCELED = "canceled", "canceled"
        COMPLETED = "completed", "completed"

    class CanceledBy(models.TextChoices):
        RENTER = "renter", "renter"
        OWNER = "owner", "owner"
        SYSTEM = "system", "system"
        NO_SHOW = "no_show", "no_show"

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
    charge_payment_intent_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Stripe PaymentIntent ID for the rental charge (base + renter fee).",
    )
    deposit_hold_id = models.CharField(max_length=120, blank=True, default="")
    renter_stripe_customer_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Cached Stripe customer id used for charges/deposit holds.",
    )
    renter_stripe_payment_method_id = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Payment method id to reuse for deposit authorization.",
    )
    deposit_attempt_count = models.PositiveIntegerField(default=0)
    deposit_authorized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When a damage deposit authorization succeeded.",
    )
    is_disputed = models.BooleanField(
        default=False,
        help_text="True when at least one dispute case is open for this booking.",
    )
    deposit_locked = models.BooleanField(
        default=False,
        help_text="When True, automatic deposit release is blocked while a dispute is active.",
    )
    totals = models.JSONField(default=dict, blank=True)
    canceled_by = models.CharField(
        max_length=16,
        choices=CanceledBy.choices,
        null=True,
        blank=True,
        help_text="Who initiated the cancellation, if any.",
    )
    canceled_reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Optional free-text description of why the booking was canceled.",
    )
    auto_canceled = models.BooleanField(
        default=False,
        help_text="True if the booking was canceled automatically by the system.",
    )
    pickup_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when owner confirmed pickup.",
    )
    before_photos_required = models.BooleanField(
        default=True,
        help_text="If True, renter must upload 'before' photos before pickup confirmation.",
    )
    before_photos_uploaded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When renter finished uploading 'before' photos for this booking.",
    )
    returned_by_renter_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When renter indicated the tool has been returned.",
    )
    return_confirmed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When owner confirmed the tool return.",
    )
    after_photos_uploaded_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When renter completed uploading 'after' photos.",
    )
    deposit_release_scheduled_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When a damage deposit release was scheduled.",
    )
    deposit_released_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the damage deposit hold was actually released.",
    )
    dispute_window_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="End of the post-return dispute window.",
    )
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
            self.Status.PAID,
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


class BookingPhoto(models.Model):
    """Photos uploaded against a booking for pickup/return verification."""

    class Role(models.TextChoices):
        BEFORE = "before", "before"
        AFTER = "after", "after"

    class Status(models.TextChoices):
        PENDING = "pending", "pending"
        ACTIVE = "active", "active"
        BLOCKED = "blocked", "blocked"

    class AVStatus(models.TextChoices):
        PENDING = "pending", "pending"
        CLEAN = "clean", "clean"
        INFECTED = "infected", "infected"
        ERROR = "error", "error"

    booking = models.ForeignKey(
        Booking,
        related_name="photos",
        on_delete=models.CASCADE,
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="booking_photos",
        on_delete=models.CASCADE,
    )
    role = models.CharField(
        max_length=16,
        choices=Role.choices,
        default=Role.BEFORE,
    )
    s3_key = models.CharField(max_length=512)
    url = models.URLField(max_length=1024, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.BigIntegerField(null=True, blank=True)
    etag = models.CharField(max_length=64, blank=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    av_status = models.CharField(
        max_length=12,
        choices=AVStatus.choices,
        default=AVStatus.PENDING,
    )
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"BookingPhoto {self.pk} for booking {self.booking_id}"
