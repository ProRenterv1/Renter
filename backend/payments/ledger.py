from datetime import datetime, time, timedelta
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
OWNER_HISTORY_KINDS = OWNER_EARNING_KINDS + [Transaction.Kind.OWNER_PAYOUT]
TWO_PLACES = Decimal("0.01")
OWNER_HOLD_HOURS = 48


def log_transaction(
    *,
    user: User,
    booking=None,
    promotion_slot=None,
    kind: str,
    amount: Decimal,
    currency: str = "cad",
    stripe_id: Optional[str] = None,
    stripe_available_on: datetime | None = None,
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
        stripe_available_on=stripe_available_on,
    )


def get_owner_earnings_queryset(user: User):
    """Return the queryset of owner-facing transactions for a user."""
    return Transaction.objects.filter(
        user=user,
        kind__in=OWNER_EARNING_KINDS,
    ).order_by("-created_at")


def get_owner_history_queryset(user: User):
    """Return the queryset of owner-facing transactions including promotion charges."""
    return Transaction.objects.filter(
        user=user,
        kind__in=OWNER_HISTORY_KINDS + [Transaction.Kind.PROMOTION_CHARGE],
    ).order_by("-created_at")


def _booking_hold_release_at(booking) -> datetime | None:
    if not booking or not getattr(booking, "end_date", None):
        return None
    end_date = booking.end_date
    end_dt = datetime.combine(end_date, time.max)
    if timezone.is_naive(end_dt):
        end_dt = timezone.make_aware(end_dt, timezone.get_current_timezone())
    return end_dt + timedelta(hours=OWNER_HOLD_HOURS)


def _promotion_charge_is_earnings(tx: Transaction) -> bool:
    stripe_id = (tx.stripe_id or "").strip().lower()
    if stripe_id.startswith("tr_") or stripe_id.startswith("earnings:"):
        return True
    promo = getattr(tx, "promotion_slot", None)
    promo_id = (getattr(promo, "stripe_session_id", "") or "").strip().lower()
    return promo_id.startswith("tr_") or promo_id.startswith("earnings:")


def _owner_transaction_available_at(tx: Transaction) -> datetime | None:
    hold_at = _booking_hold_release_at(getattr(tx, "booking", None))
    stripe_available_on = getattr(tx, "stripe_available_on", None)
    if stripe_available_on and timezone.is_naive(stripe_available_on):
        stripe_available_on = timezone.make_aware(
            stripe_available_on, timezone.get_current_timezone()
        )
    if hold_at and stripe_available_on:
        return max(hold_at, stripe_available_on)
    return hold_at or stripe_available_on


def compute_owner_available_balance(user: User) -> Decimal:
    """Return the owner's spendable balance based on ledger + availability rules."""
    spendable_kinds = [
        Transaction.Kind.OWNER_EARNING,
        Transaction.Kind.REFUND,
        Transaction.Kind.OWNER_PAYOUT,
        Transaction.Kind.PROMOTION_CHARGE,
    ]
    now = timezone.now()
    total = Decimal("0.00")
    qs = Transaction.objects.filter(user=user, kind__in=spendable_kinds).select_related(
        "booking",
        "promotion_slot",
    )
    for tx in qs:
        amount = Decimal(tx.amount)
        if tx.kind == Transaction.Kind.PROMOTION_CHARGE:
            if _promotion_charge_is_earnings(tx):
                total -= abs(amount)
            continue
        if amount <= Decimal("0.00"):
            total += amount
            continue
        if tx.kind == Transaction.Kind.OWNER_EARNING:
            available_at = _owner_transaction_available_at(tx)
            if available_at and available_at > now:
                continue
        total += amount
    return total.quantize(TWO_PLACES)


def compute_owner_total_balance(user: User) -> Decimal:
    """Return total owner balance (available + pending), net of payouts."""
    spendable_kinds = [
        Transaction.Kind.OWNER_EARNING,
        Transaction.Kind.REFUND,
        Transaction.Kind.OWNER_PAYOUT,
        Transaction.Kind.PROMOTION_CHARGE,
    ]
    total = Decimal("0.00")
    qs = Transaction.objects.filter(user=user, kind__in=spendable_kinds).select_related(
        "promotion_slot",
    )
    for tx in qs:
        amount = Decimal(tx.amount)
        if tx.kind == Transaction.Kind.PROMOTION_CHARGE:
            if _promotion_charge_is_earnings(tx):
                total -= abs(amount)
            continue
        total += amount
    return total.quantize(TWO_PLACES)


def compute_owner_balances(user: User) -> dict[str, str]:
    """Compute lifetime and recent earnings figures for an owner."""
    queryset = get_owner_earnings_queryset(user)

    lifetime_gross = Decimal("0.00")
    owner_earnings_total = Decimal("0.00")
    lifetime_refunds = Decimal("0.00")
    lifetime_deposit_captured = Decimal("0.00")
    lifetime_deposit_released = Decimal("0.00")
    last_30_days_net = Decimal("0.00")
    cutoff = timezone.now() - timedelta(days=30)

    for tx in queryset:
        amount = Decimal(tx.amount)
        if tx.kind == Transaction.Kind.OWNER_EARNING:
            if amount > 0:
                lifetime_gross += amount
            owner_earnings_total += amount
        elif tx.kind == Transaction.Kind.REFUND:
            lifetime_refunds += amount
        elif tx.kind == Transaction.Kind.DAMAGE_DEPOSIT_CAPTURE and amount > 0:
            lifetime_deposit_captured += amount
        elif tx.kind == Transaction.Kind.DAMAGE_DEPOSIT_RELEASE and amount > 0:
            lifetime_deposit_released += amount

        if tx.created_at >= cutoff:
            last_30_days_net += amount

    net_earnings = owner_earnings_total
    net_earnings += lifetime_deposit_captured
    net_earnings += lifetime_deposit_released
    net_earnings += lifetime_refunds

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
