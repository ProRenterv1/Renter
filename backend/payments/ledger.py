from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from .models import Transaction


def log_transaction(
    *,
    user,
    kind: str,
    direction: str,
    amount: Decimal,
    booking=None,
    listing=None,
    description: str = "",
    currency: str = "CAD",
    stripe_payment_intent_id: str = "",
    stripe_charge_id: str = "",
    stripe_balance_txn_id: str = "",
    metadata: Optional[dict] = None,
) -> Transaction:
    """
    Persist a Transaction row, converting Decimal dollars to integer cents.
    """

    metadata = metadata or {}
    cents = int((amount * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return Transaction.objects.create(
        user=user,
        kind=kind,
        direction=direction,
        amount_cents=cents,
        booking=booking,
        listing=listing,
        description=description,
        currency=currency,
        stripe_payment_intent_id=stripe_payment_intent_id,
        stripe_charge_id=stripe_charge_id,
        stripe_balance_txn_id=stripe_balance_txn_id,
        metadata=metadata,
    )
