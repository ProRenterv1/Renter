from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class Listing(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
    )
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    daily_price_cad = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        default=0,
    )
    city = models.CharField(max_length=60, default="Edmonton")
    is_active = models.BooleanField(default=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if not self.title or len(self.title.strip()) < 3:
            raise ValidationError("Title too short")
        if self.daily_price_cad and self.daily_price_cad > 10000:
            raise ValidationError("Unreasonable price")

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:120] or "listing"
            count = type(self).objects.count() + 1
            self.slug = f"{base}-{self.owner_id or 'u'}-{count}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} ({self.slug})"


class ListingPhoto(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACTIVE = "active", "Active"
        BLOCKED = "blocked", "Blocked"

    class AVStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        CLEAN = "clean", "Clean"
        INFECTED = "infected", "Infected"
        ERROR = "error", "Error"

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listing_photos",
    )
    key = models.CharField(max_length=512)
    url = models.URLField(max_length=1024)
    filename = models.CharField(max_length=255, blank=True)
    content_type = models.CharField(max_length=120, blank=True)
    size = models.BigIntegerField(null=True, blank=True)
    etag = models.CharField(max_length=64, blank=True)
    av_status = models.CharField(
        max_length=12,
        choices=AVStatus.choices,
        default=AVStatus.PENDING,
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Photo {self.id} for listing {self.listing_id}"
