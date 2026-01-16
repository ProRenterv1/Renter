from django.conf import settings
from django.db import models


class Transaction(models.Model):
    class Kind(models.TextChoices):
        BOOKING_CHARGE = "BOOKING_CHARGE", "Booking charge"
        REFUND = "REFUND", "Refund"
        OWNER_EARNING = "OWNER_EARNING", "Owner earning"
        OWNER_PAYOUT = "OWNER_PAYOUT", "Owner payout"
        PLATFORM_FEE = "PLATFORM_FEE", "Platform fee"
        GST_COLLECTED = "GST_COLLECTED", "GST collected"
        DAMAGE_DEPOSIT_HOLD = "DAMAGE_DEPOSIT_HOLD", "Damage deposit hold"
        DAMAGE_DEPOSIT_CAPTURE = "DAMAGE_DEPOSIT_CAPTURE", "Damage deposit capture"
        DAMAGE_DEPOSIT_RELEASE = "DAMAGE_DEPOSIT_RELEASE", "Damage deposit release"
        PROMOTION_CHARGE = "PROMOTION_CHARGE", "Promotion charge"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
    )
    promotion_slot = models.ForeignKey(
        "promotions.PromotedSlot",
        on_delete=models.CASCADE,
        related_name="transactions",
        null=True,
        blank=True,
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
    stripe_available_on = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Stripe balance transaction available_on timestamp (UTC).",
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
    business_type = models.CharField(
        max_length=32,
        default="individual",
        help_text="Stripe business_type (individual/company) chosen by the owner.",
    )
    is_fully_onboarded = models.BooleanField(
        default=False,
        help_text="Charges and payouts enabled, no disabled_reason.",
    )
    transit_number = models.CharField(max_length=16, blank=True, default="")
    institution_number = models.CharField(max_length=16, blank=True, default="")
    account_number = models.CharField(max_length=32, blank=True, default="")
    lifetime_instant_payouts = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default="0.00",
        help_text="Total gross amount ever sent via instant payouts.",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_synced_at", "user_id"]

    def __str__(self) -> str:
        return f"{self.user} - {self.stripe_account_id}"


class OwnerFeeTaxInvoice(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_fee_invoices",
    )
    period_start = models.DateField()
    period_end = models.DateField()
    fee_subtotal = models.DecimalField(max_digits=10, decimal_places=2, default="0.00")
    gst = models.DecimalField(max_digits=10, decimal_places=2, default="0.00")
    total = models.DecimalField(max_digits=10, decimal_places=2, default="0.00")
    invoice_number = models.CharField(max_length=64, unique=True)
    gst_number_snapshot = models.CharField(max_length=64, blank=True, default="")
    pdf_s3_key = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-period_start", "-created_at"]
        unique_together = [("owner", "period_start", "period_end")]

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.owner_id})"


class PaymentMethod(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="payment_methods",
        on_delete=models.CASCADE,
    )
    stripe_payment_method_id = models.CharField(max_length=255, unique=True)
    brand = models.CharField(max_length=32, blank=True, default="")
    last4 = models.CharField(max_length=4, blank=True, default="")
    exp_month = models.PositiveSmallIntegerField(null=True, blank=True)
    exp_year = models.PositiveSmallIntegerField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        unique_together = [("user", "stripe_payment_method_id")]

    def __str__(self) -> str:
        return f"{self.user} {self.brand} ****{self.last4}"


class PaymentSetupIntent(models.Model):
    """Locally caches Stripe SetupIntent metadata for card saves."""

    class IntentType(models.TextChoices):
        DEFAULT_CARD = "default_card", "Default card"
        PROMOTION_CARD = "promotion_card", "Promotion card"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="payment_setup_intents",
        on_delete=models.CASCADE,
    )
    intent_type = models.CharField(
        max_length=64,
        choices=IntentType.choices,
        default=IntentType.DEFAULT_CARD,
    )
    stripe_setup_intent_id = models.CharField(max_length=255, unique=True)
    client_secret = models.TextField()
    status = models.CharField(max_length=64, default="requires_confirmation")
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "intent_type"]),
            models.Index(fields=["user", "consumed_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} setup_intent={self.stripe_setup_intent_id} ({self.intent_type})"
