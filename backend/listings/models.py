from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    icon = models.CharField(
        max_length=80,
        blank=True,
        help_text="Lucide icon component name to render for this category.",
    )
    accent = models.CharField(
        max_length=80,
        blank=True,
        help_text="CSS background color (e.g., Tailwind token or CSS variable).",
    )
    icon_color = models.CharField(
        max_length=80,
        blank=True,
        help_text="CSS color for the icon (e.g., Tailwind token or CSS variable).",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "Listing category"
        verbose_name_plural = "Listing categories"

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug and self.name:
            max_length = self._meta.get_field("slug").max_length
            base_slug = slugify(self.name)[:max_length] or "category"
            slug_candidate = base_slug
            counter = 1
            while type(self).objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                suffix = f"-{counter}"
                trimmed = base_slug[: max_length - len(suffix)] or "category"
                slug_candidate = f"{trimmed}{suffix}"
                counter += 1
            self.slug = slug_candidate
        super().save(*args, **kwargs)


class Listing(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
    )
    title = models.CharField(max_length=140)
    description = models.TextField(blank=True)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        related_name="listings",
        null=True,
        blank=True,
        help_text="Optional category for this listing.",
    )
    daily_price_cad = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        default=Decimal("1.00"),
    )
    replacement_value_cad = models.DecimalField(
        "Replacement value (CAD)",
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        default=Decimal("0"),
    )
    damage_deposit_cad = models.DecimalField(
        "Damage deposit (CAD)",
        max_digits=9,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
        default=Decimal("0"),
    )
    is_available = models.BooleanField(
        default=True,
        help_text="Owner-controlled availability flag for rentals.",
    )
    city = models.CharField(max_length=60, default="Edmonton")
    postal_code = models.CharField(
        max_length=12,
        blank=True,
        default="",
        help_text="Optional postal code to approximate the item's location.",
    )
    is_active = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        """Enforce Listing-specific business rules before persisting."""
        super().clean()

        errors = {}

        title = (self.title or "").strip()
        if len(title) < 3:
            errors.setdefault("title", []).append("Title must be at least 3 characters long.")

        price = self.daily_price_cad
        if price is None or price <= 0:
            errors.setdefault("daily_price_cad", []).append("Price per day must be greater than 0.")

        if self.replacement_value_cad is not None and self.replacement_value_cad < 0:
            errors.setdefault("replacement_value_cad", []).append(
                "Replacement value cannot be negative."
            )

        if self.damage_deposit_cad is not None and self.damage_deposit_cad < 0:
            errors.setdefault("damage_deposit_cad", []).append("Damage deposit cannot be negative.")

        self.postal_code = (self.postal_code or "").strip().upper()

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        if not self.slug:
            base = slugify(self.title)[:120] or "listing"
            count = type(self).objects.count() + 1
            self.slug = f"{base}-{self.owner_id or 'u'}-{count}"
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.title} ({self.slug})"

    class Meta:
        indexes = [
            models.Index(fields=["is_deleted", "deleted_at"]),
        ]


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

    class Meta:
        indexes = [
            models.Index(fields=["listing"]),
        ]

    def __str__(self) -> str:
        return f"Photo {self.id} for listing {self.listing_id}"
