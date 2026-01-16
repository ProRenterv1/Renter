from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from bookings.models import Booking
from listings.models import Listing
from payments.ledger import compute_owner_available_balance, log_transaction
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


def test_log_transaction_creates_row(owner_user, booking):
    txn = log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.BOOKING_CHARGE,
        amount=Decimal("10.50"),
    )

    assert Transaction.objects.count() == 1
    assert txn.amount == Decimal("10.50")
    assert txn.currency == "cad"
    assert txn.kind == Transaction.Kind.BOOKING_CHARGE
    assert txn.booking == booking
    assert txn.user == owner_user
    assert txn.stripe_id is None


def test_log_transaction_allows_custom_currency_and_stripe_id(owner_user, booking):
    txn = log_transaction(
        user=owner_user,
        booking=booking,
        kind=Transaction.Kind.PLATFORM_FEE,
        amount=Decimal("5.00"),
        currency="usd",
        stripe_id="pi_123",
    )

    assert txn.currency == "usd"
    assert txn.stripe_id == "pi_123"


def test_owner_available_balance_respects_booking_and_stripe_holds(
    owner_user, listing, renter_user
):
    today = timezone.localdate()
    held_booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=today - timedelta(days=1),
        end_date=today,
    )
    log_transaction(
        user=owner_user,
        booking=held_booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("100.00"),
    )

    available_booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=today - timedelta(days=5),
        end_date=today - timedelta(days=3),
    )
    log_transaction(
        user=owner_user,
        booking=available_booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("50.00"),
    )

    delayed_booking = Booking.objects.create(
        listing=listing,
        owner=owner_user,
        renter=renter_user,
        start_date=today - timedelta(days=5),
        end_date=today - timedelta(days=3),
    )
    log_transaction(
        user=owner_user,
        booking=delayed_booking,
        kind=Transaction.Kind.OWNER_EARNING,
        amount=Decimal("25.00"),
        stripe_available_on=timezone.now() + timedelta(hours=6),
    )

    assert compute_owner_available_balance(owner_user) == Decimal("50.00")
