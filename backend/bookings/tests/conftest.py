"""Shared fixtures for bookings tests."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

import pytest
from django.contrib.auth import get_user_model

from bookings.models import Booking
from listings.models import Listing

User = get_user_model()


@pytest.fixture
def owner_user():
    return User.objects.create_user(
        username="owner",
        password="testpass",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def renter_user():
    return User.objects.create_user(
        username="renter",
        password="testpass",
        can_list=False,
        can_rent=True,
    )


@pytest.fixture
def other_user():
    return User.objects.create_user(
        username="other",
        password="testpass",
        can_list=True,
        can_rent=True,
    )


@pytest.fixture
def listing(owner_user):
    return Listing.objects.create(
        owner=owner_user,
        title="Pro Camera Kit",
        description="Mirrorless camera with two lenses.",
        daily_price_cad=Decimal("45.00"),
        replacement_value_cad=Decimal("1500.00"),
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
    ) -> Booking:
        selected_listing = listing_override or listing
        return Booking.objects.create(
            listing=selected_listing,
            owner=owner or selected_listing.owner,
            renter=renter or renter_user,
            start_date=start_date,
            end_date=end_date,
            status=status,
        )

    return _create_booking
