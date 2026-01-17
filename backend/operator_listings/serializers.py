from rest_framework import serializers

from identity.models import is_user_identity_verified
from listings.models import Category, Listing, ListingPhoto
from operator_core.models import OperatorNote


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


class OperatorListingOwnerSummarySerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True, allow_blank=True)
    name = serializers.SerializerMethodField()
    city = serializers.CharField(read_only=True, allow_blank=True)

    def get_name(self, obj):
        return _display_name(obj)


class OperatorListingOwnerDetailSerializer(OperatorListingOwnerSummarySerializer):
    phone = serializers.CharField(read_only=True, allow_blank=True)
    email_verified = serializers.BooleanField(read_only=True)
    phone_verified = serializers.BooleanField(read_only=True)
    identity_verified = serializers.SerializerMethodField()

    def get_identity_verified(self, obj):
        annotated_value = getattr(obj, "identity_verified", None)
        if isinstance(annotated_value, bool):
            return annotated_value
        payout_account = getattr(obj, "payout_account", None)
        if payout_account is not None:
            return bool(getattr(payout_account, "is_fully_onboarded", False))
        return is_user_identity_verified(obj)


class OperatorListingCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug"]
        read_only_fields = fields


class OperatorListingPhotoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    url = serializers.URLField(read_only=True)
    ordering = serializers.IntegerField(read_only=True)


class OperatorListingListSerializer(serializers.ModelSerializer):
    owner = OperatorListingOwnerSummarySerializer(read_only=True)
    category = OperatorListingCategorySerializer(read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    needs_review = serializers.SerializerMethodField()
    daily_price_cad = serializers.DecimalField(max_digits=8, decimal_places=2, read_only=True)

    class Meta:
        model = Listing
        fields = [
            "id",
            "title",
            "owner",
            "city",
            "category",
            "daily_price_cad",
            "is_active",
            "is_deleted",
            "deleted_at",
            "needs_review",
            "thumbnail_url",
            "created_at",
        ]
        read_only_fields = fields

    def _first_photo(self, obj: Listing):
        photos = getattr(obj, "prefetched_photos", None)
        if photos:
            return photos[0]
        return obj.photos.order_by("created_at", "id").first()

    def get_thumbnail_url(self, obj: Listing) -> str | None:
        photo = self._first_photo(obj)
        return getattr(photo, "url", None) or None

    def get_needs_review(self, obj: Listing) -> bool:
        annotated = getattr(obj, "needs_review", None)
        if isinstance(annotated, bool):
            return annotated
        return OperatorNote.objects.filter(
            content_type__model=obj._meta.model_name,
            object_id=str(obj.pk),
            tags__name="needs_review",
        ).exists()


class OperatorListingDetailSerializer(OperatorListingListSerializer):
    owner = OperatorListingOwnerDetailSerializer(read_only=True)
    photos = serializers.SerializerMethodField()
    description = serializers.CharField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    postal_code = serializers.CharField(read_only=True)
    replacement_value_cad = serializers.DecimalField(
        max_digits=10, decimal_places=2, read_only=True
    )
    damage_deposit_cad = serializers.DecimalField(max_digits=9, decimal_places=2, read_only=True)

    class Meta(OperatorListingListSerializer.Meta):
        fields = [
            "id",
            "title",
            "description",
            "owner",
            "city",
            "postal_code",
            "category",
            "daily_price_cad",
            "replacement_value_cad",
            "damage_deposit_cad",
            "is_active",
            "is_deleted",
            "deleted_at",
            "is_available",
            "needs_review",
            "photos",
            "thumbnail_url",
            "created_at",
        ]
        read_only_fields = fields

    def get_photos(self, obj: Listing):
        photos = getattr(obj, "prefetched_photos", None)
        if photos is None:
            photos = list(obj.photos.all().order_by("created_at", "id"))
        payload = [
            {"id": photo.id, "url": photo.url, "ordering": idx}
            for idx, photo in enumerate(photos)
            if isinstance(photo, ListingPhoto)
        ]
        serializer = OperatorListingPhotoSerializer(payload, many=True)
        return serializer.data
