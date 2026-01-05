from __future__ import annotations

from typing import Any

from rest_framework import serializers

from bookings.models import Booking
from chat.models import Conversation, Message
from notifications.models import NotificationLog


def _get_user_label(user) -> str:
    if not user:
        return ""
    name_callable = getattr(user, "get_full_name", None)
    if callable(name_callable):
        name = name_callable()
        if name:
            return name
    return getattr(user, "email", None) or getattr(user, "username", "") or f"User {user.id}"


class OperatorConversationMixin:
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

    def get_participants(self, obj: Conversation) -> list[dict[str, Any]]:
        owner = obj.owner
        renter = obj.renter
        return [
            {
                "user_id": owner.id if owner else None,
                "name": _get_user_label(owner),
                "email": getattr(owner, "email", None),
                "avatar_url": getattr(owner, "avatar_url", None),
            },
            {
                "user_id": renter.id if renter else None,
                "name": _get_user_label(renter),
                "email": getattr(renter, "email", None),
                "avatar_url": getattr(renter, "avatar_url", None),
            },
        ]

    def get_status(self, obj: Conversation) -> str:
        booking = getattr(obj, "booking", None)
        if booking and getattr(booking, "is_disputed", False):
            return "disputed"
        if not obj.is_active:
            return "inactive"
        if booking:
            if booking.status in {Booking.Status.CANCELED, Booking.Status.COMPLETED}:
                return "inactive"
            return "booking_related"
        return "pre_booking"

    def get_unread_count(self, obj: Conversation) -> int:
        return 0


class OperatorConversationListSerializer(OperatorConversationMixin, serializers.ModelSerializer):
    booking_id = serializers.SerializerMethodField()
    listing_id = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message_at = serializers.DateTimeField(read_only=True, allow_null=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "booking_id",
            "listing_id",
            "listing_title",
            "participants",
            "status",
            "unread_count",
            "last_message_at",
            "created_at",
        ]


class OperatorMessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(allow_null=True)
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender_id",
            "sender_name",
            "message_type",
            "system_kind",
            "text",
            "created_at",
        ]

    def get_sender_name(self, obj: Message) -> str:
        if obj.message_type == Message.MESSAGE_TYPE_SYSTEM or not obj.sender:
            return "System"
        return _get_user_label(obj.sender)


class OperatorNotificationLogSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(allow_null=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = NotificationLog
        fields = [
            "id",
            "type",
            "channel",
            "status",
            "created_at",
            "user_id",
            "user_name",
        ]

    def get_user_name(self, obj: NotificationLog) -> str:
        return _get_user_label(obj.user)


class OperatorConversationDetailSerializer(OperatorConversationMixin, serializers.ModelSerializer):
    booking_id = serializers.SerializerMethodField()
    listing_id = serializers.SerializerMethodField()
    listing_title = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message_at = serializers.DateTimeField(read_only=True, allow_null=True)
    messages = serializers.SerializerMethodField()
    notifications = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "booking_id",
            "listing_id",
            "listing_title",
            "participants",
            "status",
            "unread_count",
            "last_message_at",
            "created_at",
            "messages",
            "notifications",
        ]

    def get_messages(self, obj: Conversation):
        messages = getattr(obj, "prefetched_messages", None)
        if messages is None:
            messages = obj.messages.select_related("sender").all()
        return OperatorMessageSerializer(messages, many=True).data

    def get_notifications(self, obj: Conversation):
        booking_id = obj.booking_id
        if not booking_id:
            return []
        logs = (
            NotificationLog.objects.filter(booking_id=booking_id)
            .select_related("user")
            .order_by("-created_at")
        )
        return OperatorNotificationLogSerializer(logs, many=True).data
