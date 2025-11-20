"""API endpoints for booking-scoped chat conversations."""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bookings.models import Booking
from bookings.serializers import BookingSerializer
from chat_models import Conversation, Message, create_user_message


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
        read_only_fields = [
            "id",
            "sender",
            "sender_is_me",
            "message_type",
            "system_kind",
            "created_at",
        ]

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


def _get_user_conversation_or_404(user, pk: int) -> Conversation:
    """Restrict conversation access to owner/renter."""
    return get_object_or_404(
        Conversation.objects.select_related(
            "booking", "booking__listing", "owner", "renter"
        ).prefetch_related("messages"),
        Q(owner=user) | Q(renter=user),
        pk=pk,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chat_list(request):
    """Return all conversations for the authenticated user."""
    user = request.user
    qs = Conversation.objects.filter(Q(owner=user) | Q(renter=user)).select_related(
        "booking",
        "booking__listing",
        "owner",
        "renter",
    )
    serializer = ConversationSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chat_detail(request, pk: int):
    """Return the full conversation history."""
    conv = _get_user_conversation_or_404(request.user, pk)
    serializer = ConversationDetailSerializer(conv, context={"request": request})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_send_message(request, pk: int):
    """Create a user-authored chat entry."""
    conv = _get_user_conversation_or_404(request.user, pk)
    booking = conv.booking
    if not conv.is_active or booking.status in {
        Booking.Status.CANCELED,
        Booking.Status.COMPLETED,
    }:
        return Response(
            {"detail": "Chat is closed for this booking."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    serializer = SendMessageSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    msg = create_user_message(conv, sender=request.user, text=serializer.validated_data["text"])

    return Response(
        MessageSerializer(msg, context={"request": request}).data,
        status=status.HTTP_201_CREATED,
    )
