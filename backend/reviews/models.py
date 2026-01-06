from __future__ import annotations

from django.conf import settings
from django.db import models


class Review(models.Model):
    class Role(models.TextChoices):
        OWNER_TO_RENTER = "owner_to_renter", "Owner to renter"
        RENTER_TO_OWNER = "renter_to_owner", "Renter to owner"

    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="reviews",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="authored_reviews",
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="received_reviews",
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "author", "role"],
                name="unique_review_per_booking_per_author_role",
            )
        ]

    def __str__(self) -> str:
        return f"Review {self.role} by {self.author_id} for booking {self.booking_id}"


def update_user_review_stats(user) -> None:
    """Recalculate rating and review_count aggregates for the given user."""
    from django.db.models import Avg, Count

    qs = Review.objects.filter(subject=user).exclude(rating__isnull=True)
    agg = qs.aggregate(avg=Avg("rating"), count=Count("id"))
    user.rating = agg.get("avg") or None
    user.review_count = agg.get("count") or 0
    user.save(update_fields=["rating", "review_count"])
