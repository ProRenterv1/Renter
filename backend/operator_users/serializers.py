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
    active_risk_flag = serializers.SerializerMethodField()
    owner_fee_exempt = serializers.SerializerMethodField()
    renter_fee_exempt = serializers.SerializerMethodField()
    fee_expires_at = serializers.SerializerMethodField()

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
            "active_risk_flag",
            "can_rent",
            "can_list",
            "is_active",
            "date_joined",
            "identity_verified",
            "owner_fee_exempt",
            "renter_fee_exempt",
            "fee_expires_at",
            *BASE_COUNT_FIELDS,
        ]
        read_only_fields = fields

    def get_identity_verified(self, obj: User) -> bool:
        annotated_value = getattr(obj, "identity_verified", None)
        if isinstance(annotated_value, bool):
            return annotated_value
        return is_user_identity_verified(obj)

    def get_active_risk_flag(self, obj: User):
        flags = getattr(obj, "active_risk_flags", None)
        flag = flags[0] if isinstance(flags, list) and flags else None

        if flag is None:
            manager = getattr(obj, "risk_flags", None)
            if manager is not None and hasattr(manager, "filter"):
                flag = (
                    manager.filter(active=True)
                    .select_related("created_by")
                    .order_by("-created_at")
                    .first()
                )

        if not flag:
            return None

        creator = getattr(flag, "created_by", None)
        creator_full_name = None
        if creator:
            full_name = creator.get_full_name() or ""
            creator_full_name = full_name.strip() or None
        creator_label = (
            creator_full_name
            or getattr(creator, "email", None)
            or getattr(creator, "username", None)
            or (f"User {creator.id}" if creator and creator.id else None)
        )

        return {
            "id": getattr(flag, "id", None),
            "level": getattr(flag, "level", None),
            "category": getattr(flag, "category", None),
            "note": getattr(flag, "note", None) or "",
            "created_at": getattr(flag, "created_at", None),
            "created_by_id": getattr(creator, "id", None),
            "created_by_label": creator_label,
        }

    def _fee_overrides(self, obj: User) -> dict[str, object]:
        try:
            return obj.active_fee_overrides()
        except Exception:
            return {"owner_fee_exempt": False, "renter_fee_exempt": False, "expires_at": None}

    def get_owner_fee_exempt(self, obj: User) -> bool:
        overrides = self._fee_overrides(obj)
        return bool(overrides.get("owner_fee_exempt"))

    def get_renter_fee_exempt(self, obj: User) -> bool:
        overrides = self._fee_overrides(obj)
        return bool(overrides.get("renter_fee_exempt"))

    def get_fee_expires_at(self, obj: User):
        overrides = self._fee_overrides(obj)
        return overrides.get("expires_at")


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
            "active_risk_flag",
            "email_verified",
            "phone_verified",
            "identity_verified",
            "date_joined",
            "last_login",
            "last_login_ip",
            "last_login_ua",
            "bookings",
            "owner_fee_exempt",
            "renter_fee_exempt",
            "fee_expires_at",
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
