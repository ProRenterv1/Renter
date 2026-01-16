import logging
from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from bookings.models import Booking
from operator_bookings.models import BookingEvent
from payments.stripe_api import (
    StripeConfigurationError,
    StripePaymentError,
    StripeTransientError,
    get_payment_intent_fee,
)


def _display_name(user) -> str:
    if not user:
        return ""
    name = (user.get_full_name() or "").strip()
    if name:
        return name
    for attr in ("username", "email"):
        value = getattr(user, attr, "") or ""
        value = value.strip()
        if value:
            return value
    if getattr(user, "id", None):
        return f"User {user.id}"
    return ""


logger = logging.getLogger(__name__)


class OperatorBookingUserSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True, allow_blank=True)
    name = serializers.SerializerMethodField()
    phone = serializers.CharField(read_only=True, allow_blank=True)
    city = serializers.CharField(read_only=True, allow_blank=True)

    def get_name(self, obj):
        return _display_name(obj)


class OperatorBookingEventSerializer(serializers.ModelSerializer):
    actor = OperatorBookingUserSerializer(read_only=True)

    class Meta:
        model = BookingEvent
        fields = ["id", "type", "payload", "actor", "created_at"]
        read_only_fields = fields


class OperatorBookingListSerializer(serializers.ModelSerializer):
    owner = OperatorBookingUserSerializer(read_only=True)
    renter = OperatorBookingUserSerializer(read_only=True)
    listing_id = serializers.IntegerField(source="listing.id", read_only=True)
    listing_title = serializers.CharField(source="listing.title", read_only=True)
    is_overdue = serializers.SerializerMethodField()
    total_charge = serializers.SerializerMethodField()
    pickup_confirmed_at = serializers.DateTimeField(read_only=True)
    returned_by_renter_at = serializers.DateTimeField(read_only=True)
    return_confirmed_at = serializers.DateTimeField(read_only=True)
    after_photos_uploaded_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Booking
        fields = [
            "id",
            "status",
            "listing_id",
            "listing_title",
            "owner",
            "renter",
            "start_date",
            "end_date",
            "is_overdue",
            "pickup_confirmed_at",
            "returned_by_renter_at",
            "return_confirmed_at",
            "after_photos_uploaded_at",
            "total_charge",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_overdue(self, obj: Booking) -> bool:
        today = timezone.localdate()
        return bool(obj.end_date and obj.end_date < today and not obj.return_confirmed_at)

    def get_total_charge(self, obj: Booking) -> str:
        totals = obj.totals or {}
        raw = totals.get("total_charge") or totals.get("rental_subtotal") or ""
        return str(raw)


class OperatorBookingDetailSerializer(OperatorBookingListSerializer):
    events = serializers.SerializerMethodField()
    disputes = serializers.SerializerMethodField()
    totals = serializers.JSONField(read_only=True)
    is_disputed = serializers.BooleanField(read_only=True)
    dispute_window_expires_at = serializers.DateTimeField(read_only=True)
    charge_payment_intent_id = serializers.CharField(read_only=True)
    deposit_hold_id = serializers.CharField(read_only=True)
    pickup_confirmed_at = serializers.DateTimeField(read_only=True)
    returned_by_renter_at = serializers.DateTimeField(read_only=True)
    return_confirmed_at = serializers.DateTimeField(read_only=True)
    after_photos_uploaded_at = serializers.DateTimeField(read_only=True)

    class Meta(OperatorBookingListSerializer.Meta):
        fields = [
            "id",
            "status",
            "listing_id",
            "listing_title",
            "owner",
            "renter",
            "start_date",
            "end_date",
            "is_overdue",
            "is_disputed",
            "dispute_window_expires_at",
            "totals",
            "charge_payment_intent_id",
            "deposit_hold_id",
            "pickup_confirmed_at",
            "returned_by_renter_at",
            "return_confirmed_at",
            "after_photos_uploaded_at",
            "events",
            "disputes",
            "created_at",
            "paid_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        totals = data.get("totals") or {}
        if totals.get("stripe_fee") not in (None, ""):
            return data
        intent_id = getattr(instance, "charge_payment_intent_id", "") or ""
        if not intent_id:
            return data
        try:
            fee_value = get_payment_intent_fee(intent_id)
        except (StripeConfigurationError, StripePaymentError, StripeTransientError) as exc:
            logger.warning(
                "operator_booking_detail: stripe fee lookup failed for booking %s: %s",
                getattr(instance, "id", "unknown"),
                str(exc) or "stripe error",
            )
            return data
        if fee_value is None:
            return data
        totals = {**totals, "stripe_fee": f"{fee_value.quantize(Decimal('0.01'))}"}
        data["totals"] = totals
        return data

    def get_events(self, obj: Booking):
        events = getattr(obj, "prefetched_events", None)
        if events is None:
            events = list(obj.events.all())

        if events:
            return OperatorBookingEventSerializer(events, many=True).data

        derived = []

        def _append(ts, type_: str, payload: dict | None = None):
            if not ts:
                return
            derived.append(
                {
                    "id": None,
                    "type": type_,
                    "payload": payload or {},
                    "actor": None,
                    "created_at": ts,
                }
            )

        _append(getattr(obj, "created_at", None), "booking_created", {"status": obj.status})
        if getattr(obj, "charge_payment_intent_id", ""):
            _append(
                getattr(obj, "created_at", None),
                "payment_intent",
                {"id": obj.charge_payment_intent_id},
            )
        _append(getattr(obj, "deposit_authorized_at", None), "deposit_authorized", {})
        _append(getattr(obj, "pickup_confirmed_at", None), "pickup_confirmed", {})
        _append(getattr(obj, "returned_by_renter_at", None), "renter_returned", {})
        _append(getattr(obj, "return_confirmed_at", None), "owner_return_confirmed", {})
        _append(getattr(obj, "deposit_release_scheduled_at", None), "deposit_release_scheduled", {})
        _append(getattr(obj, "deposit_released_at", None), "deposit_released", {})

        derived.sort(
            key=lambda e: e["created_at"] or timezone.datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        for idx, item in enumerate(derived):
            item["id"] = -(idx + 1)
        return derived

    def get_disputes(self, obj: Booking):
        cases = getattr(obj, "prefetched_disputes", None)
        if cases is None:
            DisputeCase = apps.get_model("disputes", "DisputeCase")
            cases = DisputeCase.objects.filter(booking=obj)
        payload = []
        for case in cases:
            payload.append(
                {
                    "id": getattr(case, "id", None),
                    "status": getattr(case, "status", None),
                    "category": getattr(case, "category", None),
                    "created_at": getattr(case, "created_at", None),
                }
            )
        return payload


class ForceCancelBookingSerializer(serializers.Serializer):
    actor = serializers.ChoiceField(choices=["system", "owner", "renter", "no_show"])
    reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class AdjustBookingDatesSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        start = attrs.get("start_date")
        end = attrs.get("end_date")
        try:
            from bookings.domain import validate_booking_dates

            validate_booking_dates(start, end)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        return attrs


class ResendBookingNotificationsSerializer(serializers.Serializer):
    TYPES = ("booking_request", "status_update", "receipt", "completed", "dispute_missing_evidence")
    types = serializers.ListField(
        child=serializers.ChoiceField(choices=TYPES), allow_empty=False, allow_null=False
    )
    reason = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
