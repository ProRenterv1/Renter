"""Serializers for booking-related API endpoints."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from identity.models import is_user_identity_verified
from listings.models import Listing, ListingPhoto
from listings.services import compute_booking_totals
from notifications import tasks as notification_tasks
from payments.stripe_api import (
    StripePaymentError,
    StripeTransientError,
    create_booking_payment_intents,
)

from .domain import ensure_no_conflict, is_return_initiated, validate_booking_dates
from .models import Booking

logger = logging.getLogger(__name__)
CURRENCY_QUANTIZE = Decimal("0.01")


def _format_currency(amount: Decimal | None) -> str:
    """Return a normalized currency string for limit messaging."""
    if amount is None:
        amount = Decimal("0")
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return f"${amount.quantize(CURRENCY_QUANTIZE)}"


class BookingSerializer(serializers.ModelSerializer):
    """Serialize Booking instances for API usage."""

    listing = serializers.PrimaryKeyRelatedField(
        queryset=Listing.objects.filter(is_active=True, is_available=True)
    )
    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    renter = serializers.PrimaryKeyRelatedField(read_only=True)
    listing_title = serializers.ReadOnlyField(source="listing.title")
    renter_first_name = serializers.ReadOnlyField(source="renter.first_name")
    renter_last_name = serializers.ReadOnlyField(source="renter.last_name")
    renter_username = serializers.ReadOnlyField(source="renter.username")
    renter_avatar_url = serializers.ReadOnlyField(source="renter.avatar_url")
    renter_identity_verified = serializers.SerializerMethodField()
    listing_owner_first_name = serializers.ReadOnlyField(source="listing.owner.first_name")
    listing_owner_last_name = serializers.ReadOnlyField(source="listing.owner.last_name")
    listing_owner_username = serializers.ReadOnlyField(source="listing.owner.username")
    listing_owner_avatar_url = serializers.ReadOnlyField(source="listing.owner.avatar_url")
    listing_owner_identity_verified = serializers.SerializerMethodField()
    listing_slug = serializers.ReadOnlyField(source="listing.slug")
    listing_primary_photo_url = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    stripe_payment_method_id = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Stripe PaymentMethod ID used to pay for this booking.",
    )
    stripe_customer_id = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        help_text="Stripe Customer ID associated with the PaymentIntents.",
    )

    class Meta:
        model = Booking
        fields = (
            "id",
            "status",
            "canceled_by",
            "canceled_reason",
            "auto_canceled",
            "start_date",
            "end_date",
            "pickup_confirmed_at",
            "before_photos_required",
            "before_photos_uploaded_at",
            "returned_by_renter_at",
            "return_confirmed_at",
            "after_photos_uploaded_at",
            "deposit_release_scheduled_at",
            "deposit_released_at",
            "dispute_window_expires_at",
            "deposit_locked",
            "is_disputed",
            "listing",
            "listing_title",
            "listing_owner_first_name",
            "listing_owner_last_name",
            "listing_owner_username",
            "listing_owner_avatar_url",
            "listing_owner_identity_verified",
            "listing_slug",
            "listing_primary_photo_url",
            "owner",
            "renter",
            "renter_first_name",
            "renter_last_name",
            "renter_username",
            "renter_avatar_url",
            "renter_identity_verified",
            "totals",
            "charge_payment_intent_id",
            "deposit_hold_id",
            "status_label",
            "stripe_payment_method_id",
            "stripe_customer_id",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "status",
            "canceled_by",
            "canceled_reason",
            "auto_canceled",
            "pickup_confirmed_at",
            "before_photos_required",
            "before_photos_uploaded_at",
            "returned_by_renter_at",
            "return_confirmed_at",
            "after_photos_uploaded_at",
            "deposit_release_scheduled_at",
            "deposit_released_at",
            "dispute_window_expires_at",
            "deposit_locked",
            "is_disputed",
            "owner",
            "renter",
            "totals",
            "charge_payment_intent_id",
            "deposit_hold_id",
            "status_label",
            "created_at",
            "updated_at",
            "listing_owner_first_name",
            "listing_owner_last_name",
            "listing_owner_username",
            "listing_slug",
            "listing_primary_photo_url",
            "listing_owner_identity_verified",
            "renter_identity_verified",
        )

    def _get_identity_cache(self) -> dict[int, bool]:
        cache = getattr(self, "_identity_cache", None)
        if cache is None:
            cache = {}
            self._identity_cache = cache
        return cache

    def _is_identity_verified(self, user) -> bool:
        user_id = getattr(user, "id", None)
        if not user_id:
            return False
        cache = self._get_identity_cache()
        if user_id in cache:
            return cache[user_id]
        result = is_user_identity_verified(user)
        cache[user_id] = result
        return result

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

        if not getattr(user, "email_verified", False) or not getattr(user, "phone_verified", False):
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Please verify both your email and phone number before renting tools."
                    ]
                }
            )

        rental_days = (end_date - start_date).days if start_date and end_date else None
        is_verified = is_user_identity_verified(user)

        if listing and start_date and end_date and not is_verified:
            max_days = settings.UNVERIFIED_MAX_BOOKING_DAYS
            max_repl = settings.UNVERIFIED_MAX_REPLACEMENT_CAD
            max_dep = settings.UNVERIFIED_MAX_DEPOSIT_CAD

            replacement = listing.replacement_value_cad or Decimal("0")
            deposit = listing.damage_deposit_cad or Decimal("0")

            if rental_days is not None and rental_days > max_days:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            f"Unverified renters can book tools for up to {max_days} days. "
                            "Please shorten your rental or complete ID verification."
                        ]
                    }
                )

            if replacement > max_repl or deposit > max_dep:
                message = (
                    "This booking is only available to users with ID verification. "
                    "Unverified profiles are limited to tools up to "
                    f"{_format_currency(max_repl)} replacement value, "
                    f"{_format_currency(max_dep)} damage deposit, "
                    f"and rentals up to {max_days} days."
                )
                raise serializers.ValidationError({"non_field_errors": [message]})

        if listing and start_date and end_date and is_verified:
            max_days_verified = settings.VERIFIED_MAX_BOOKING_DAYS
            if rental_days is not None and rental_days > max_days_verified:
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            (
                                f"Bookings are limited to {max_days_verified} days at a time. "
                                "Please shorten your rental period."
                            )
                        ]
                    }
                )

        if listing and listing.owner_id == user.id:
            raise serializers.ValidationError(
                {"listing": ["You cannot create bookings for your own listing."]}
            )

        if listing and start_date and end_date:
            # Conflicts are checked only against confirmed/paid bookings;
            # requested overlaps are allowed.
            ensure_no_conflict(listing, start_date, end_date)

        return attrs

    def create(self, validated_data: dict[str, Any]) -> Booking:
        """
        Create a booking, collect payment, and notify the listing owner.

        Steps: compute totals, persist the booking, confirm the rental charge PaymentIntent,
        place a manual-capture deposit hold, and queue the owner notification. Stripe calls
        use booking-scoped idempotency keys so transient retries are safe and won't double-charge.
        """
        request = self.context["request"]
        user = request.user
        listing: Listing = validated_data["listing"]
        start_date = validated_data["start_date"]
        end_date = validated_data["end_date"]
        payment_method_id = validated_data.pop("stripe_payment_method_id", "") or ""
        customer_id = validated_data.pop("stripe_customer_id", "") or ""

        totals = compute_booking_totals(
            listing=listing,
            start_date=start_date,
            end_date=end_date,
        )

        with transaction.atomic():
            booking = Booking.objects.create(
                listing=listing,
                owner=listing.owner,
                renter=user,
                start_date=start_date,
                end_date=end_date,
                status=Booking.Status.REQUESTED,
                totals=totals,
                deposit_hold_id="",
                charge_payment_intent_id="",
            )

            if payment_method_id:
                try:
                    charge_id, deposit_id = create_booking_payment_intents(
                        booking=booking,
                        customer_id=customer_id,
                        payment_method_id=payment_method_id,
                    )
                except StripeTransientError:
                    logger.warning(
                        "Stripe transient error on booking creation",
                        exc_info=True,
                        extra={"booking_id": booking.id, "listing_id": listing.id},
                    )
                    raise serializers.ValidationError(
                        {"non_field_errors": ["Temporary payment issue, please retry."]}
                    )
                except StripePaymentError as exc:
                    message = str(exc) or "Payment could not be completed."
                    logger.info(
                        "Stripe payment error on booking creation: %s",
                        message,
                        extra={"booking_id": booking.id},
                    )
                    raise serializers.ValidationError({"non_field_errors": [message]})

                booking.charge_payment_intent_id = charge_id or ""
                booking.deposit_hold_id = deposit_id or ""
                booking.save(
                    update_fields=[
                        "charge_payment_intent_id",
                        "deposit_hold_id",
                        "updated_at",
                    ]
                )

        try:
            notification_tasks.send_booking_request_email.delay(listing.owner_id, booking.id)
        except Exception:
            logger.info(
                "notifications: could not queue send_booking_request_email",
                exc_info=True,
            )

        return booking

    @staticmethod
    def _display_label_for_status(status: str) -> str:
        mapping = {
            Booking.Status.REQUESTED: "Requested",
            Booking.Status.CONFIRMED: "Pending",
            Booking.Status.PAID: "Waiting pick up",
            Booking.Status.COMPLETED: "Completed",
            Booking.Status.CANCELED: "Canceled",
        }
        return mapping.get(status, "Requested")

    def get_status_label(self, booking: Booking) -> str:
        """
        Return a renter-facing display label for the booking status.

        Bookings that collected a charge (intent ID set) should continue to show
        their paid state even if the status was later reset to "requested".
        """

        status_value = booking.status
        if status_value == Booking.Status.REQUESTED and booking.charge_payment_intent_id:
            status_value = Booking.Status.PAID
        if is_return_initiated(booking):
            return "Return pending"
        if status_value == Booking.Status.PAID and booking.pickup_confirmed_at:
            return "In progress"

        return self._display_label_for_status(status_value)

    def get_listing_primary_photo_url(self, booking: Booking) -> str | None:
        """Return the first approved photo URL for the related listing."""
        listing = getattr(booking, "listing", None)
        if not listing:
            return None
        photo = (
            listing.photos.filter(
                status=ListingPhoto.Status.ACTIVE,
                av_status=ListingPhoto.AVStatus.CLEAN,
            )
            .order_by("id")
            .first()
        )
        return photo.url if photo else None

    def get_renter_identity_verified(self, booking: Booking) -> bool:
        return self._is_identity_verified(getattr(booking, "renter", None))

    def get_listing_owner_identity_verified(self, booking: Booking) -> bool:
        listing = getattr(booking, "listing", None)
        owner = getattr(listing, "owner", None) if listing else None
        return self._is_identity_verified(owner)
