from django.conf import settings
from django.db import models


class Transaction(models.Model):
    class Kind(models.TextChoices):
        BOOKING_CHARGE = "BOOKING_CHARGE", "Booking charge"
        REFUND = "REFUND", "Refund"
        OWNER_EARNING = "OWNER_EARNING", "Owner earning"
        PLATFORM_FEE = "PLATFORM_FEE", "Platform fee"
        DAMAGE_DEPOSIT_CAPTURE = "DAMAGE_DEPOSIT_CAPTURE", "Damage deposit capture"
        DAMAGE_DEPOSIT_RELEASE = "DAMAGE_DEPOSIT_RELEASE", "Damage deposit release"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    kind = models.CharField(max_length=64, choices=Kind.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=8, default="cad")
    stripe_id = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Related Stripe PaymentIntent / Charge / Refund id.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} {self.kind} {self.amount} {self.currency}"


class OwnerPayoutAccount(models.Model):
    """Stripe Connect Express account tracking for listing owners."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payout_account",
    )
    stripe_account_id = models.CharField(max_length=255)
    payouts_enabled = models.BooleanField(default=False)
    charges_enabled = models.BooleanField(default=False)
    requirements_due = models.JSONField(default=dict, blank=True)
    is_fully_onboarded = models.BooleanField(
        default=False,
        help_text="Charges and payouts enabled, no disabled_reason.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_synced_at", "user_id"]

    def __str__(self) -> str:
        return f"{self.user} - {self.stripe_account_id}"
