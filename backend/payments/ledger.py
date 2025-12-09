from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Transaction

User = get_user_model()
OWNER_EARNING_KINDS = [
    Transaction.Kind.OWNER_EARNING,
    Transaction.Kind.REFUND,
    Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE,
    Transaction.Kind.DAMAGE_DEPOSIT_RELEASE,
]
TWO_PLACES = Decimal("0.01")


def log_transaction(
    *,
    user: User,
    booking=None,
    promotion_slot=None,
    kind: str,
    amount: Decimal,
    currency: str = "cad",
    stripe_id: Optional[str] = None,
) -> Transaction:
    """
    Create and return a Transaction row.

    This is a thin helper; no complex business logic here yet.
    """
    return Transaction.objects.create(
        user=user,
        booking=booking,
        promotion_slot=promotion_slot,
        kind=kind,
        amount=amount,
        currency=currency,
        stripe_id=stripe_id,
    )


def get_owner_earnings_queryset(user: User):
    """Return the queryset of owner-facing transactions for a user."""
    return Transaction.objects.filter(
        user=user,
        kind__in=OWNER_EARNING_KINDS,
    ).order_by("-created_at")


def compute_owner_balances(user: User) -> dict[str, str]:
    """Compute lifetime and recent earnings figures for an owner."""
    queryset = get_owner_earnings_queryset(user)

    lifetime_gross = Decimal("0.00")
    lifetime_refunds = Decimal("0.00")
    lifetime_deposit_captured = Decimal("0.00")
    lifetime_deposit_released = Decimal("0.00")
    last_30_days_net = Decimal("0.00")
    cutoff = timezone.now() - timedelta(days=30)

    for tx in queryset:
        amount = Decimal(tx.amount)
        if tx.kind == Transaction.Kind.OWNER_EARNING and amount > 0:
            lifetime_gross += amount
        elif tx.kind == Transaction.Kind.REFUND:
            lifetime_refunds += amount
        elif tx.kind == Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE and amount > 0:
            lifetime_deposit_captured += amount
        elif tx.kind == Transaction.Kind.DAMAGE_DEPOSIT_RELEASE and amount > 0:
            lifetime_deposit_released += amount

        if tx.created_at >= cutoff:
            last_30_days_net += amount

    net_earnings = (
        lifetime_gross + lifetime_deposit_captured + lifetime_deposit_released + lifetime_refunds
    )

    def _format(value: Decimal) -> str:
        return f"{value.quantize(TWO_PLACES)}"

    return {
        "lifetime_gross_earnings": _format(lifetime_gross),
        "lifetime_refunds": _format(lifetime_refunds),
        "lifetime_deposit_captured": _format(lifetime_deposit_captured),
        "lifetime_deposit_released": _format(lifetime_deposit_released),
        "net_earnings": _format(net_earnings),
        "last_30_days_net": _format(last_30_days_net),
    }
