"""Serializers for chat conversations."""

from __future__ import annotations

from rest_framework import serializers

from bookings.serializers import BookingSerializer
from chat.models import Conversation, Message, get_unread_message_count
from identity.models import is_user_identity_verified


class ConversationSerializer(serializers.ModelSerializer):
    """Summarize a conversation for list views."""

    booking_id = serializers.SerializerMethodField()
    listing_id = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    other_party_name = serializers.SerializerMethodField()
    other_party_avatar_url = serializers.SerializerMethodField()
    other_party_identity_verified = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "booking_id",
            "listing_id",
            "listing_title",
            "other_party_name",
            "other_party_avatar_url",
            "other_party_identity_verified",
            "is_active",
            "last_message",
            "last_message_at",
            "unread_count",
        ]

    def _get_listing(self, obj: Conversation):
        if obj.booking and getattr(obj.booking, "listing", None):
            return obj.booking.listing
        return getattr(obj, "listing", None)

    def get_booking_id(self, obj: Conversation) -> int | None:
        return obj.booking_id

    def get_listing_id(self, obj: Conversation) -> int | None:
        listing = self._get_listing(obj)
        return getattr(listing, "id", None) if listing else None

    def get_listing_title(self, obj: Conversation) -> str:
        listing = self._get_listing(obj)
        return getattr(listing, "title", "") if listing else ""

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

    def _get_other_party(self, obj: Conversation):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return obj.owner if user and obj.renter_id == user.id else obj.renter

    def get_other_party_name(self, obj: Conversation) -> str:
        other = self._get_other_party(obj)
        name_callable = getattr(other, "get_full_name", None)
        if callable(name_callable):
            name = name_callable()
            if name:
                return name
        return getattr(other, "email", None) or getattr(other, "username", "")

    def get_other_party_avatar_url(self, obj: Conversation):
        other = self._get_other_party(obj)
        return getattr(other, "avatar_url", None)

    def get_other_party_identity_verified(self, obj: Conversation) -> bool:
        other = self._get_other_party(obj)
        return self._is_identity_verified(other)

    def _get_last_message(self, obj: Conversation) -> Message | None:
        if hasattr(obj, "_last_message_cache"):
            return obj._last_message_cache  # type: ignore[attr-defined]
        msg = obj.messages.order_by("-created_at").first()
        obj._last_message_cache = msg  # type: ignore[attr-defined]
        return msg

    def get_last_message(self, obj: Conversation):
        msg = self._get_last_message(obj)
        if not msg:
            return None
        request = self.context.get("request")
        user = getattr(request, "user", None)
        sender_id = msg.sender_id
        sender_is_me = bool(user and sender_id is not None and user.id == sender_id)
        read_state = getattr(obj, "_read_state", None)
        last_read_id = getattr(read_state, "last_read_message_id", None)
        return {
            "id": msg.id,
            "sender_id": sender_id,
            "sender_is_me": sender_is_me,
            "message_type": msg.message_type,
            "system_kind": msg.system_kind,
            "text": msg.text,
            "created_at": msg.created_at,
            "is_read": bool(sender_is_me or (last_read_id is not None and msg.id <= last_read_id)),
        }

    def get_last_message_at(self, obj: Conversation):
        msg = self._get_last_message(obj)
        return msg.created_at if msg else None

    def get_unread_count(self, obj: Conversation) -> int:
        cached = getattr(obj, "_unread_count", None)
        if cached is not None:
            return cached
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return get_unread_message_count(obj, user)


class MessageSerializer(serializers.ModelSerializer):
    """Render chat messages with sender metadata."""

    sender_is_me = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender",
            "sender_is_me",
            "is_read",
            "message_type",
            "system_kind",
            "text",
            "created_at",
        ]
        read_only_fields = fields

    def get_sender_is_me(self, obj: Message) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return bool(user and obj.sender_id == user.id)

    def get_is_read(self, obj: Message) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        sender_id = obj.sender_id
        if user and sender_id == user.id:
            other_read_state = self.context.get("other_read_state")
            other_last_read_id = getattr(other_read_state, "last_read_message_id", None)
            return bool(other_last_read_id and obj.id <= other_last_read_id)

        read_state = self.context.get("read_state")
        last_read_id = getattr(read_state, "last_read_message_id", None)
        return bool(last_read_id and obj.id <= last_read_id)


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Detailed representation of a single conversation."""

    booking = BookingSerializer(read_only=True)
    listing_id = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    listing_primary_photo_url = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "booking",
            "listing_id",
            "listing_title",
            "listing_primary_photo_url",
            "is_active",
            "messages",
        ]

    def _get_listing(self, obj: Conversation):
        if obj.booking and getattr(obj.booking, "listing", None):
            return obj.booking.listing
        return getattr(obj, "listing", None)

    def get_listing_id(self, obj: Conversation):
        listing = self._get_listing(obj)
        return getattr(listing, "id", None) if listing else None

    def get_listing_title(self, obj: Conversation):
        listing = self._get_listing(obj)
        return getattr(listing, "title", "") if listing else ""

    def get_listing_primary_photo_url(self, obj: Conversation):
        listing = self._get_listing(obj)
        if not listing:
            return None
        photo = (
            listing.photos.filter(
                status=listing.photos.model.Status.ACTIVE,  # type: ignore[attr-defined]
                av_status=listing.photos.model.AVStatus.CLEAN,  # type: ignore[attr-defined]
            )
            .order_by("id")
            .first()
        )
        return photo.url if photo else None

    def get_messages(self, obj: Conversation):
        serializer = MessageSerializer(
            obj.messages.all(),
            many=True,
            read_only=True,
            context=self.context,
        )
        return serializer.data


class SendMessageSerializer(serializers.Serializer):
    """Validate incoming chat messages."""

    text = serializers.CharField(max_length=2000)

    def validate_text(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Message cannot be empty.")
        return cleaned
