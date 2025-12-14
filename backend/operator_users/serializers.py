from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework import serializers

from bookings.models import Booking
from identity.models import is_user_identity_verified

User = get_user_model()

BASE_COUNT_FIELDS = [
    "listings_count",
    "bookings_as_renter_count",
    "bookings_as_owner_count",
    "disputes_count",
]


class OperatorUserListSerializer(serializers.ModelSerializer):
    listings_count = serializers.IntegerField(read_only=True)
    bookings_as_renter_count = serializers.IntegerField(read_only=True)
    bookings_as_owner_count = serializers.IntegerField(read_only=True)
    disputes_count = serializers.IntegerField(read_only=True)
    identity_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "email_verified",
            "phone",
            "phone_verified",
            "username",
            "first_name",
            "last_name",
            "city",
            "can_rent",
            "can_list",
            "is_active",
            "date_joined",
            "identity_verified",
            *BASE_COUNT_FIELDS,
        ]
        read_only_fields = fields

    def get_identity_verified(self, obj: User) -> bool:
        annotated_value = getattr(obj, "identity_verified", None)
        if isinstance(annotated_value, bool):
            return annotated_value
        return is_user_identity_verified(obj)


class OperatorUserDetailSerializer(OperatorUserListSerializer):
    last_login_ip = serializers.SerializerMethodField()
    last_login_ua = serializers.SerializerMethodField()
    bookings = serializers.SerializerMethodField()

    class Meta(OperatorUserListSerializer.Meta):
        fields = [
            "id",
            "email",
            "phone",
            "username",
            "first_name",
            "last_name",
            "street_address",
            "city",
            "province",
            "postal_code",
            "can_rent",
            "can_list",
            "is_active",
            "email_verified",
            "phone_verified",
            "identity_verified",
            "date_joined",
            "last_login",
            "last_login_ip",
            "last_login_ua",
            "bookings",
            *BASE_COUNT_FIELDS,
        ]
        read_only_fields = fields

    def get_last_login_ip(self, obj: User):
        return getattr(obj, "last_login_ip", None)

    def get_last_login_ua(self, obj: User):
        return getattr(obj, "last_login_ua", None)

    def get_bookings(self, obj: User):
        owner_related = getattr(obj, "bookings_as_owner", None)
        renter_related = getattr(obj, "bookings_as_renter", None)
        owner_bookings = list(owner_related.all()[:50]) if owner_related is not None else []
        renter_bookings = list(renter_related.all()[:50]) if renter_related is not None else []
        combined = []
        for booking in owner_bookings:
            combined.append((booking, "owner"))
        for booking in renter_bookings:
            combined.append((booking, "renter"))

        combined.sort(key=lambda pair: getattr(pair[0], "created_at", None) or 0, reverse=True)

        def _counterparty(role: str, booking: Booking):
            other = booking.renter if role == "owner" else booking.owner
            name = (other.get_full_name() or other.username or other.email or "").strip()
            return name or f"User {other.id}"

        def _amount_from_totals(totals: dict | None) -> str:
            if not isinstance(totals, dict):
                return ""
            raw = totals.get("total_charge") or totals.get("rental_subtotal")
            try:
                return str(Decimal(str(raw)))
            except Exception:
                return ""

        payload = []
        for booking, role in combined[:50]:
            listing_title = getattr(getattr(booking, "listing", None), "title", "") or ""
            payload.append(
                {
                    "id": booking.id,
                    "status": booking.status,
                    "listing_title": listing_title,
                    "other_party": _counterparty(role, booking),
                    "amount": _amount_from_totals(booking.totals),
                    "end_date": getattr(booking, "end_date", None),
                    "role": role,
                }
            )
        return payload
