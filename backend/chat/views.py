"""Chat API views."""

from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from bookings.models import Booking
from chat.models import (
    Conversation,
    ConversationReadState,
    create_user_message,
    get_or_create_listing_conversation,
    get_unread_message_count,
    mark_conversation_read,
)
from chat.serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
    MessageSerializer,
    SendMessageSerializer,
)
from listings.models import Listing


def _get_user_conversation_or_404(user, pk: int) -> Conversation:
    """Restrict conversation access to owner/renter."""
    return get_object_or_404(
        Conversation.objects.select_related(
            "booking",
            "booking__listing",
            "listing",
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
    qs = list(
        Conversation.objects.filter(Q(owner=user) | Q(renter=user)).select_related(
            "booking",
            "booking__listing",
            "listing",
            "owner",
            "renter",
        )
    )
    states = {
        state.conversation_id: state
        for state in ConversationReadState.objects.filter(
            user=user, conversation__in=[conv.id for conv in qs]
        )
    }
    for conv in qs:
        conv._read_state = states.get(conv.id)
        conv._unread_count = get_unread_message_count(conv, user)

    serializer = ConversationSerializer(qs, many=True, context={"request": request})
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chat_detail(request, pk: int):
    """Return the full conversation history."""
    conv = _get_user_conversation_or_404(request.user, pk)
    read_state = mark_conversation_read(conv, request.user)
    other_user_id = conv.owner_id if request.user.id == conv.renter_id else conv.renter_id
    other_read_state = None
    if other_user_id:
        other_read_state = ConversationReadState.objects.filter(
            conversation=conv,
            user_id=other_user_id,
        ).first()
    serializer = ConversationDetailSerializer(
        conv,
        context={
            "request": request,
            "read_state": read_state,
            "other_read_state": other_read_state,
        },
    )
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_start_for_listing(request):
    """
    Create or fetch a conversation between the current user (as renter)
    and the owner of the given listing, before any booking exists.

    Request body: { "listing": <listing_id> }
    Response: ConversationDetailSerializer.
    """
    listing_id = request.data.get("listing")
    try:
        listing_id = int(listing_id)
    except (TypeError, ValueError):
        return Response(
            {"detail": "listing is required and must be an integer."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    listing = get_object_or_404(Listing.objects.filter(is_deleted=False), pk=listing_id)
    user = request.user

    if user.id == listing.owner_id:
        return Response(
            {"detail": "You cannot start a chat with your own listing."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    conv = get_or_create_listing_conversation(listing, renter=user)

    read_state = mark_conversation_read(conv, user)
    other_user_id = conv.owner_id if user.id == conv.renter_id else conv.renter_id
    other_read_state = None
    if other_user_id:
        other_read_state = ConversationReadState.objects.filter(
            conversation=conv,
            user_id=other_user_id,
        ).first()

    serializer = ConversationDetailSerializer(
        conv,
        context={
            "request": request,
            "read_state": read_state,
            "other_read_state": other_read_state,
        },
    )
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_send_message(request, pk: int):
    """Create a user-authored chat entry."""
    conv = _get_user_conversation_or_404(request.user, pk)
    booking = conv.booking

    if not conv.is_active:
        return Response(
            {"detail": "Chat is closed for this conversation."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if booking is not None and booking.status in {
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
