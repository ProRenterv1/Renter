"""Serializers for chat conversations."""

from __future__ import annotations

from rest_framework import serializers

from bookings.serializers import BookingSerializer
from chat.models import Conversation, Message


class ConversationSerializer(serializers.ModelSerializer):
    """Summarize a conversation for list views."""

    booking_id = serializers.IntegerField(source="booking.id", read_only=True)
    listing_title = serializers.CharField(source="booking.listing.title", read_only=True)
    other_party_name = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "booking_id",
            "listing_title",
            "other_party_name",
            "is_active",
            "last_message",
            "last_message_at",
        ]

    def get_other_party_name(self, obj: Conversation) -> str:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        other = obj.owner if user and obj.renter_id == user.id else obj.renter
        name_callable = getattr(other, "get_full_name", None)
        if callable(name_callable):
            name = name_callable()
            if name:
                return name
        return getattr(other, "email", None) or getattr(other, "username", "")

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
        return {
            "id": msg.id,
            "message_type": msg.message_type,
            "system_kind": msg.system_kind,
            "text": msg.text,
            "created_at": msg.created_at,
        }

    def get_last_message_at(self, obj: Conversation):
        msg = self._get_last_message(obj)
        return msg.created_at if msg else None


class MessageSerializer(serializers.ModelSerializer):
    """Render chat messages with sender metadata."""

    sender_is_me = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender",
            "sender_is_me",
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


class ConversationDetailSerializer(serializers.ModelSerializer):
    """Detailed representation of a single conversation."""

    booking = BookingSerializer(read_only=True)
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = ["id", "booking", "is_active", "messages"]


class SendMessageSerializer(serializers.Serializer):
    """Validate incoming chat messages."""

    text = serializers.CharField(max_length=2000)

    def validate_text(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("Message cannot be empty.")
        return cleaned
