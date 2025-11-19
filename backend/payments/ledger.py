from decimal import Decimal
from typing import Optional

from django.contrib.auth import get_user_model

from .models import Transaction

User = get_user_model()


def log_transaction(
    *,
    user: User,
    booking,
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
        kind=kind,
        amount=amount,
        currency=currency,
        stripe_id=stripe_id,
    )
