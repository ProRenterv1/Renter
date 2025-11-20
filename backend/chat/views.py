"""Chat API views."""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bookings.models import Booking
from chat.models import Conversation, create_user_message
from chat.serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
    MessageSerializer,
    SendMessageSerializer,
)


def _get_user_conversation_or_404(user, pk: int) -> Conversation:
    """Restrict conversation access to owner/renter."""
    return get_object_or_404(
        Conversation.objects.select_related(
            "booking",
            "booking__listing",
            "owner",
            "renter",
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
