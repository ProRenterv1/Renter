from rest_framework import serializers

from .models import Category, Listing, ListingPhoto


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
    category = serializers.SlugRelatedField(
        slug_field="slug",
        queryset=Category.objects.all(),
        required=False,
        allow_null=True,
    )
    category_name = serializers.ReadOnlyField(source="category.name")

    class Meta:
        model = Listing
        fields = [
            "id",
            "slug",
            "owner",
            "owner_username",
            "title",
            "description",
            "daily_price_cad",
            "replacement_value_cad",
            "damage_deposit_cad",
            "city",
            "category",
            "category_name",
            "is_active",
            "is_available",
            "photos",
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

    def create(self, validated_data):
        """Create a listing for the authenticated user if allowed."""
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError({"detail": "Authentication required."})
        if not getattr(user, "can_list", False):
            raise serializers.ValidationError({"detail": "You are not allowed to create listings."})
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
