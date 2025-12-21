from __future__ import annotations

from rest_framework import serializers

from promotions.models import PromotedSlot


class OperatorPromotionSerializer(serializers.ModelSerializer):
    listing_title = serializers.CharField(source="listing.title", read_only=True)
    owner_name = serializers.SerializerMethodField()
    owner_email = serializers.EmailField(source="owner.email", read_only=True)

    class Meta:
        model = PromotedSlot
        fields = [
            "id",
            "listing",
            "listing_title",
            "owner",
            "owner_name",
            "owner_email",
            "price_per_day_cents",
            "base_price_cents",
            "gst_cents",
            "total_price_cents",
            "starts_at",
            "ends_at",
            "active",
            "stripe_session_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_owner_name(self, obj: PromotedSlot) -> str:
        owner = getattr(obj, "owner", None)
        if not owner:
            return ""
        name = (getattr(owner, "get_full_name", lambda: "")() or "").strip()
        return name or getattr(owner, "username", "")
