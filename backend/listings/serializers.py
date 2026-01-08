from decimal import Decimal

from django.conf import settings
from rest_framework import serializers

from identity.models import is_user_identity_verified
from promotions.cache import get_active_promoted_listing_ids

from .models import Category, Listing, ListingPhoto

CURRENCY_QUANTIZE = Decimal("0.01")


def _format_currency(amount: Decimal | None) -> str:
    """Return a normalized currency string for ID verification messaging."""
    if amount is None:
        amount = Decimal("0")
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    return f"${amount.quantize(CURRENCY_QUANTIZE)}"


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "accent", "icon_color"]
        read_only_fields = ["id", "slug"]


class ListingPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingPhoto
        fields = [
            "id",
            "listing",
            "owner",
            "key",
            "url",
            "filename",
            "content_type",
            "size",
            "etag",
            "status",
            "av_status",
            "width",
            "height",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "listing",
            "owner",
            "key",
            "url",
            "filename",
            "content_type",
            "size",
            "etag",
            "status",
            "av_status",
            "width",
            "height",
            "created_at",
            "updated_at",
        ]


class ListingSerializer(serializers.ModelSerializer):
    """Serializer for Listing that enforces business rules and permissions."""

    owner = serializers.PrimaryKeyRelatedField(read_only=True)
    photos = serializers.SerializerMethodField()
    owner_username = serializers.ReadOnlyField(source="owner.username")
    owner_first_name = serializers.ReadOnlyField(source="owner.first_name")
    owner_last_name = serializers.ReadOnlyField(source="owner.last_name")
    category = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
    )
    category_name = serializers.ReadOnlyField(source="category.name")
    is_promoted = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            "id",
            "slug",
            "owner",
            "owner_username",
            "owner_first_name",
            "owner_last_name",
            "title",
            "description",
            "daily_price_cad",
            "replacement_value_cad",
            "damage_deposit_cad",
            "city",
            "postal_code",
            "category",
            "category_name",
            "is_active",
            "is_available",
            "photos",
            "is_promoted",
            "created_at",
        ]
        read_only_fields = ["owner", "slug", "created_at"]

    def get_photos(self, obj):
        """Return only photos that passed moderation and AV scans."""
        qs = obj.photos.filter(
            status=ListingPhoto.Status.ACTIVE,
            av_status=ListingPhoto.AVStatus.CLEAN,
        )
        serializer = ListingPhotoSerializer(qs, many=True, context=self.context)
        return serializer.data

    def validate(self, attrs):
        """Enforce ID verification limits for high-value listings."""
        attrs = super().validate(attrs)
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated or is_user_identity_verified(user):
            return attrs

        replacement = attrs.get("replacement_value_cad")
        deposit = attrs.get("damage_deposit_cad")

        if self.instance:
            if replacement is None:
                replacement = self.instance.replacement_value_cad
            if deposit is None:
                deposit = self.instance.damage_deposit_cad

        replacement = replacement or Decimal("0")
        deposit = deposit or Decimal("0")
        max_repl = settings.UNVERIFIED_MAX_REPLACEMENT_CAD
        max_dep = settings.UNVERIFIED_MAX_DEPOSIT_CAD

        if replacement > max_repl or deposit > max_dep:
            message = (
                "To list tools with higher replacement value or damage deposit, please complete "
                "ID verification. Unverified owners are limited to "
                f"{_format_currency(max_repl)} replacement and {_format_currency(max_dep)} "
                "damage deposit per listing."
            )
            raise serializers.ValidationError({"non_field_errors": [message]})

        return attrs

    def create(self, validated_data):
        """Create a listing for the authenticated user if allowed."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"detail": "Authentication required."})
        if not getattr(user, "can_list", False):
            raise serializers.ValidationError({"detail": "You are not allowed to create listings."})
        if not getattr(user, "email_verified", False):
            raise serializers.ValidationError(
                {"detail": "Please verify your email before creating listings."}
            )
        if not getattr(user, "phone_verified", False):
            raise serializers.ValidationError(
                {"detail": "Please verify your phone before creating listings."}
            )
        validated_data["owner"] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """Allow updates only when performed by the owner."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or instance.owner_id != getattr(user, "id", None):
            raise serializers.ValidationError(
                {"detail": "You do not have permission to modify this listing."}
            )
        if not getattr(user, "can_list", False):
            raise serializers.ValidationError({"detail": "You are not allowed to create listings."})
        if not getattr(user, "email_verified", False):
            raise serializers.ValidationError(
                {"detail": "Please verify your email before creating listings."}
            )
        if not getattr(user, "phone_verified", False):
            raise serializers.ValidationError(
                {"detail": "Please verify your phone before creating listings."}
            )
        validated_data.pop("owner", None)
        return super().update(instance, validated_data)

    def validate_daily_price_cad(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError("Price per day must be greater than 0.")
        return value

    def validate_replacement_value_cad(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Replacement value cannot be negative.")
        return value

    def validate_damage_deposit_cad(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Damage deposit cannot be negative.")
        return value

    def get_is_promoted(self, obj) -> bool:
        annotated = getattr(obj, "is_promoted", None)
        if annotated is not None:
            return bool(annotated)
        promoted_ids = get_active_promoted_listing_ids()
        return obj.id in promoted_ids
