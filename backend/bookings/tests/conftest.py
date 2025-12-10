"""Shared fixtures for bookings tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from bookings.models import Booking
from listings.models import Listing
from payments.models import OwnerPayoutAccount

User = get_user_model()


def _create_user(*, username: str, can_list: bool, can_rent: bool) -> User:
    return User.objects.create_user(
        username=username,
        password="testpass",
        can_list=can_list,
        can_rent=can_rent,
        email_verified=True,
        phone_verified=True,
    )


def _mark_verified(user: User, suffix: str) -> None:
    OwnerPayoutAccount.objects.create(
        user=user,
        stripe_account_id=f"acct_test_{suffix}",
        payouts_enabled=True,
        charges_enabled=True,
        is_fully_onboarded=True,
        requirements_due={
            "currently_due": [],
            "eventually_due": [],
            "past_due": [],
            "disabled_reason": "",
        },
        last_synced_at=timezone.now(),
    )


@pytest.fixture
def owner_user():
    user = _create_user(username="owner", can_list=True, can_rent=True)
    _mark_verified(user, "owner")
    return user


@pytest.fixture
def renter_user():
    user = _create_user(username="renter", can_list=False, can_rent=True)
    _mark_verified(user, "renter")
    return user


@pytest.fixture
def unverified_renter_user():
    return _create_user(username="unverified-renter", can_list=False, can_rent=True)


@pytest.fixture
def other_user():
    user = _create_user(username="other", can_list=True, can_rent=True)
    _mark_verified(user, "other")
    return user


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Pro Camera Kit",
        description="Mirrorless camera with two lenses.",
        daily_price_cad=Decimal("45.00"),
        replacement_value_cad=Decimal("900.00"),
        damage_deposit_cad=Decimal("250.00"),
        city="Edmonton",
        is_active=True,
        is_available=True,
    )


@pytest.fixture
def booking_factory(listing, owner_user, renter_user) -> Callable[..., Booking]:
    def _create_booking(
        *,
        listing_override: Listing | None = None,
        owner=None,
        renter=None,
        start_date,
        end_date,
        status=Booking.Status.REQUESTED,
        **extra_fields,
    ) -> Booking:
        selected_listing = listing_override or listing
        return Booking.objects.create(
            listing=selected_listing,
            owner=owner or selected_listing.owner,
            renter=renter or renter_user,
            start_date=start_date,
            end_date=end_date,
            status=status,
            **extra_fields,
        )

    return _create_booking
