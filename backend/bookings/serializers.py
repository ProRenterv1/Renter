"""Serializers for booking-related API endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from listings.models import Listing

from .domain import ensure_no_conflict, validate_booking_dates
from .models import Booking


class BookingSerializer(serializers.ModelSerializer):
    """Serialize Booking instances for API usage."""

    listing = serializers.PrimaryKeyRelatedField(
        queryset=Listing.objects.filter(is_active=True, is_available=True)
    )
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    renter = serializers.PrimaryKeyRelatedField(read_only=True)
    listing_title = serializers.ReadOnlyField(source="listing.title")

    class Meta:
        model = Booking
        fields = (
            "id",
            "status",
            "start_date",
            "end_date",
            "listing",
            "listing_title",
            "owner",
            "renter",
            "totals",
            "deposit_hold_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "owner",
            "renter",
            "totals",
            "deposit_hold_id",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate booking creation payload."""
        request = self.context.get("request")
        user = getattr(request, "user", None)

        listing: Listing = attrs.get("listing")
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")

        validate_booking_dates(start_date, end_date)

        if start_date and start_date < timezone.localdate():
            raise serializers.ValidationError({"start_date": ["Start date cannot be in the past."]})

        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"non_field_errors": ["Authentication required."]})

        if not getattr(user, "can_rent", False):
            raise serializers.ValidationError(
                {"non_field_errors": ["Your account is not allowed to rent items."]}
            )

        if listing and listing.owner_id == user.id:
            raise serializers.ValidationError(
                {"listing": ["You cannot create bookings for your own listing."]}
            )

        if listing and start_date and end_date:
            ensure_no_conflict(listing, start_date, end_date)

        return attrs

    def create(self, validated_data: dict[str, Any]) -> Booking:
        """Create a new booking with computed totals."""
        request = self.context["request"]
        user = request.user
        listing: Listing = validated_data["listing"]
        start_date = validated_data["start_date"]
        end_date = validated_data["end_date"]

        days = (end_date - start_date).days
        price_per_day: Decimal = listing.daily_price_cad
        rental_subtotal = price_per_day * days
        service_fee = (rental_subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
        damage_deposit = listing.damage_deposit_cad
        total_charge = rental_subtotal + service_fee + damage_deposit

        totals = {
            "days": str(days),
            "daily_price_cad": str(price_per_day),
            "rental_subtotal": str(rental_subtotal),
            "service_fee": str(service_fee),
            "damage_deposit": str(damage_deposit),
            "total_charge": str(total_charge),
        }

        return Booking.objects.create(
            listing=listing,
            owner=listing.owner,
            renter=user,
            start_date=start_date,
            end_date=end_date,
            status=Booking.Status.REQUESTED,
            totals=totals,
            deposit_hold_id="",
        )
