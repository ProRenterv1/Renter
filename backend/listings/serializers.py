from rest_framework import serializers

from .models import Listing, ListingPhoto


class ListingPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingPhoto
        fields = [
            "id",
            "key",
            "url",
            "status",
            "width",
            "height",
            "created_at",
        ]


class ListingSerializer(serializers.ModelSerializer):
    photos = ListingPhotoSerializer(many=True, read_only=True)
    owner_username = serializers.ReadOnlyField(source="owner.username")

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
            "city",
            "is_active",
            "photos",
            "created_at",
        ]
        read_only_fields = ["owner", "slug", "created_at"]

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)
