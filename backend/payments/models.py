from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q


class Transaction(models.Model):
    class Direction(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    class Kind(models.TextChoices):
        BOOKING_CHARGE = "booking_charge", "Booking charge"
        DAMAGE_DEPOSIT_HOLD = "damage_deposit_hold", "Damage deposit hold"
        DAMAGE_DEPOSIT_CAPTURE = "damage_deposit_capture", "Damage deposit capture"
        DAMAGE_DEPOSIT_RELEASE = "damage_deposit_release", "Damage deposit release"
        OWNER_EARNING = "owner_earning", "Owner earning"
        PLATFORM_FEE = "platform_fee", "Platform fee"
        PROMOTION_PURCHASE = "promotion_purchase", "Promotion purchase"
        REFUND = "refund", "Refund"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="transactions",
        on_delete=models.CASCADE,
    )
    booking = models.ForeignKey(
        "bookings.Booking",
        related_name="transactions",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    listing = models.ForeignKey(
        "listings.Listing",
        related_name="transactions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    direction = models.CharField(max_length=8, choices=Direction.choices)
    kind = models.CharField(max_length=32, choices=Kind.choices)
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=8, default="CAD")
    stripe_payment_intent_id = models.CharField(max_length=120, blank=True, default="")
    stripe_charge_id = models.CharField(max_length=120, blank=True, default="")
    stripe_balance_txn_id = models.CharField(max_length=120, blank=True, default="")
    description = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    effective_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["booking"]),
            models.Index(fields=["stripe_balance_txn_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "stripe_balance_txn_id"],
                name="uniq_user_balance_txn",
                condition=~Q(stripe_balance_txn_id=""),
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.user} {self.get_direction_display()} "
            f"{self.amount} {self.currency} ({self.get_kind_display()})"
        )

    @property
    def amount(self) -> Decimal:
        return (Decimal(self.amount_cents) / Decimal("100")).quantize(Decimal("0.01"))
