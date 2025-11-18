from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from bookings.models import Booking
from listings.models import Listing
from payments.ledger import log_transaction
from payments.models import Transaction

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def owner_user():
    return User.objects.create_user(username="owner", password="test-pass")


@pytest.fixture
def renter_user():
    return User.objects.create_user(username="renter", password="test-pass")


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Cordless Drill",
        description="Drill description",
        daily_price_cad=Decimal("25.00"),
        replacement_value_cad=Decimal("200.00"),
        damage_deposit_cad=Decimal("50.00"),
        city="Edmonton",
        postal_code="T5K 2M5",
        is_active=True,
        is_available=True,
    )


@pytest.fixture
def booking(listing, owner_user, renter_user):
    return Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 2),
    )


def test_log_transaction_creates_row(owner_user, listing, booking):
    txn = log_transaction(
        user=owner_user,
        kind=Transaction.Kind.BOOKING_CHARGE,
        direction=Transaction.Direction.DEBIT,
        amount=Decimal("10.50"),
        booking=booking,
        listing=listing,
        description="Booking charge",
    )

    assert Transaction.objects.count() == 1
    assert txn.amount_cents == 1050
    assert txn.amount == Decimal("10.50")
    assert txn.direction == Transaction.Direction.DEBIT
    assert txn.kind == Transaction.Kind.BOOKING_CHARGE
    assert txn.booking == booking
    assert txn.listing == listing


def test_log_transaction_metadata_default_empty_dict(owner_user):
    txn = log_transaction(
        user=owner_user,
        kind=Transaction.Kind.OWNER_EARNING,
        direction=Transaction.Direction.CREDIT,
        amount=Decimal("5.00"),
        metadata=None,
    )

    assert txn.metadata == {}


def test_log_transaction_accepts_zero_balance_txn_id(owner_user):
    txn = log_transaction(
        user=owner_user,
        kind=Transaction.Kind.PLATFORM_FEE,
        direction=Transaction.Direction.DEBIT,
        amount=Decimal("1.00"),
        stripe_balance_txn_id="",
    )

    assert txn.stripe_balance_txn_id == ""
