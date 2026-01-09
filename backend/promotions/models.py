from django.conf import settings
from django.db import models
from django.utils import timezone


class PromotedSlotQuerySet(models.QuerySet):
    def active_for_feed(self, now=None):
        current_time = now or timezone.now()
        return self.filter(
            active=True,
            starts_at__lte=current_time,
            ends_at__gt=current_time,
        )


class PromotedSlot(models.Model):
    """
    Represents a concrete promotion purchased for a listing.
    """

    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.CASCADE,
        related_name="promoted_slots",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="promoted_slots",
    )
    price_per_day_cents = models.PositiveIntegerField(default=0)
    base_price_cents = models.PositiveIntegerField(default=0)
    gst_cents = models.PositiveIntegerField(default=0)
    total_price_cents = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    active = models.BooleanField(default=True)
    stripe_session_id = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PromotedSlotQuerySet.as_manager()

    class Meta:
        ordering = ("-starts_at",)
        indexes = [
            models.Index(
                fields=("listing", "active", "starts_at", "ends_at"),
                name="promo_listing_active_dates_idx",
            ),
            models.Index(
                fields=("owner", "active"),
                name="promo_owner_active_idx",
            ),
            models.Index(
                fields=("active", "starts_at", "ends_at"),
                name="promo_active_window_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"Promoted slot for {self.listing} ({self.starts_at} - {self.ends_at})"

    @classmethod
    def active_for_feed(cls, now=None):
        return cls.objects.active_for_feed(now=now)


class PromotionCheckoutSession(models.Model):
    """Cached Checkout Sessions for card-based promotion purchases."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="promotion_checkout_sessions",
    )
    listing = models.ForeignKey(
        "listings.Listing",
        on_delete=models.CASCADE,
        related_name="promotion_checkout_sessions",
    )
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    amount_cents = models.PositiveIntegerField()
    stripe_session_id = models.CharField(max_length=255, unique=True)
    session_url = models.TextField()
    status = models.CharField(max_length=32, default="open")
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("listing", "owner"), name="promo_checkout_listing_owner_idx"),
            models.Index(fields=("owner", "consumed_at"), name="promo_checkout_owner_consumed_idx"),
        ]

    def __str__(self) -> str:
        return f"Checkout session {self.stripe_session_id} for listing {self.listing_id}"
