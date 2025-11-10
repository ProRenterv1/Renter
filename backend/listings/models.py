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
        PENDING = "PENDING", "Pending"
        CLEAN = "CLEAN", "Clean"
        BLOCKED = "BLOCKED", "Blocked"

    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    key = models.CharField(max_length=512)
    url = models.URLField(max_length=1024)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    width = models.IntegerField(null=True, blank=True)
    height = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Photo {self.id} for {self.listing_id}"
