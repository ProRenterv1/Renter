from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from rest_framework import serializers

from bookings.models import Booking

from .models import Review, update_user_review_stats

User = get_user_model()


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.PrimaryKeyRelatedField(read_only=True)
    subject = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False,
    )

    class Meta:
        model = Review
        fields = (
            "id",
            "booking",
            "author",
            "subject",
            "role",
            "rating",
            "text",
            "created_at",
        )
        read_only_fields = ("id", "author", "created_at")

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        booking = attrs.get("booking")
        if not booking:
            raise serializers.ValidationError({"booking": "This field is required."})
        try:
            booking = Booking.objects.select_related("owner", "renter").get(pk=booking.pk)
        except Booking.DoesNotExist as exc:
            raise serializers.ValidationError({"booking": "Booking not found."}) from exc

        role = attrs.get("role")
        subject = attrs.get("subject")
        rating = attrs.get("rating")

        if rating is not None and (rating < 1 or rating > 5):
            raise serializers.ValidationError({"rating": "Rating must be between 1 and 5."})

        if booking.status == Booking.Status.COMPLETED:
            booking_in_review_window = True
        else:
            booking_in_review_window = (
                booking.status == Booking.Status.PAID and booking.returned_by_renter_at is not None
            )
        if not booking_in_review_window:
            raise serializers.ValidationError("Reviews are only allowed after completion.")

        if user.id not in (booking.owner_id, booking.renter_id):
            raise serializers.ValidationError("You can only review your own bookings.")

        expected_subject = None
        if role == Review.Role.OWNER_TO_RENTER:
            if user.id != booking.owner_id:
                raise serializers.ValidationError("Only the owner can leave this review.")
            expected_subject = booking.renter
        elif role == Review.Role.RENTER_TO_OWNER:
            if user.id != booking.renter_id:
                raise serializers.ValidationError("Only the renter can leave this review.")
            expected_subject = booking.owner
        else:
            raise serializers.ValidationError({"role": "Select a valid review role."})

        if subject and subject != expected_subject:
            raise serializers.ValidationError({"subject": "Subject does not match booking."})

        attrs["booking"] = booking
        attrs["subject"] = expected_subject

        if user == expected_subject:
            raise serializers.ValidationError("Author and subject must be different users.")

        exists = Review.objects.filter(booking=booking, author=user, role=role).exists()
        if exists:
            raise serializers.ValidationError("You already left this review for this booking.")

        return attrs

    def create(self, validated_data: dict[str, Any]) -> Review:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        validated_data["author"] = user
        review = Review.objects.create(**validated_data)
        update_user_review_stats(review.subject)
        return review


class PublicReviewSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()
    author_initials = serializers.SerializerMethodField()
    author_avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = (
            "id",
            "role",
            "rating",
            "text",
            "created_at",
            "author_name",
            "author_initials",
            "author_avatar_url",
        )
        read_only_fields = fields

    def get_author_name(self, obj: Review) -> str:
        user = getattr(obj, "author", None)
        if not user:
            return "User"
        full_name = (getattr(user, "get_full_name", lambda: "")() or "").strip()
        if full_name:
            return full_name
        return getattr(user, "username", "") or "User"

    def get_author_initials(self, obj: Review) -> str:
        name = self.get_author_name(obj)
        parts = name.split()
        if parts:
            return "".join(p[0].upper() for p in parts if p)[:2] or "U"
        username = getattr(getattr(obj, "author", None), "username", "") or "U"
        return username[:2].upper()

    def get_author_avatar_url(self, obj: Review) -> str:
        user = getattr(obj, "author", None)
        if not user:
            return ""
        return getattr(user, "avatar_url", "") or ""
