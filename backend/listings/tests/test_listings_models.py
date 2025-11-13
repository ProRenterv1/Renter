from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from listings.models import Category, Listing

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def owner():
    return User.objects.create_user(
        username="model-owner",
        password="x",
        can_list=True,
        can_rent=True,
    )


def build_listing(owner, **overrides):
    data = {
        "owner": owner,
        "title": "Test Listing",
        "description": "Test item description",
        "daily_price_cad": Decimal("10.00"),
        "replacement_value_cad": Decimal("100.00"),
        "damage_deposit_cad": Decimal("25.00"),
        "city": "Edmonton",
    }
    data.update(overrides)
    return Listing(**data)


def test_listing_daily_price_must_be_positive(owner):
    listing = build_listing(owner, daily_price_cad=Decimal("0"))
    with pytest.raises(ValidationError) as exc:
        listing.full_clean()
    assert "daily_price_cad" in exc.value.message_dict
    assert "greater than or equal to" in exc.value.message_dict["daily_price_cad"][0]


def test_listing_replacement_value_cannot_be_negative(owner):
    listing = build_listing(owner, replacement_value_cad=Decimal("-1.00"))
    with pytest.raises(ValidationError) as exc:
        listing.full_clean()
    assert "replacement_value_cad" in exc.value.message_dict
    assert "greater than or equal to" in exc.value.message_dict["replacement_value_cad"][0]


def test_listing_damage_deposit_cannot_be_negative(owner):
    listing = build_listing(owner, damage_deposit_cad=Decimal("-0.01"))
    with pytest.raises(ValidationError) as exc:
        listing.full_clean()
    assert "damage_deposit_cad" in exc.value.message_dict
    assert "greater than or equal to" in exc.value.message_dict["damage_deposit_cad"][0]


def test_listing_valid_values_pass_clean(owner):
    listing = build_listing(owner)
    # Should not raise
    listing.full_clean()


def test_category_slug_auto_unique():
    cat1 = Category.objects.create(name="Camping Gear")
    cat2 = Category.objects.create(name="Camping Gear!")
    assert cat1.slug.startswith("camping-gear")
    assert cat2.slug.startswith("camping-gear")
    assert cat1.slug != cat2.slug


def test_listing_is_available_defaults_true(owner):
    listing = Listing.objects.create(
        owner=owner,
        title="Default Availability",
        description="Test availability",
        daily_price_cad=Decimal("15.00"),
        replacement_value_cad=Decimal("150.00"),
        damage_deposit_cad=Decimal("30.00"),
        city="Calgary",
    )
    assert listing.is_available is True
