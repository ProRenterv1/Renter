"""Chat conversation models and helper utilities."""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.redis import push_event

if TYPE_CHECKING:  # pragma: no cover
    from bookings.models import Booking
    from users.models import User


class Conversation(models.Model):
    """One chat thread per booking between owner and renter."""

    booking = models.OneToOneField(
        "bookings.Booking",
        on_delete=models.CASCADE,
        related_name="conversation",
        unique=True,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="owner_conversations",
    )
    renter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="renter_conversations",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        db_table = "bookings_conversation"

    def __str__(self) -> str:
        return f"Conversation(b={self.booking_id}, active={self.is_active})"


class Message(models.Model):
    """Individual chat message, either user-generated or system-generated."""

    MESSAGE_TYPE_USER = "user"
    MESSAGE_TYPE_SYSTEM = "system"
    MESSAGE_TYPE_CHOICES = [
        (MESSAGE_TYPE_USER, "User"),
        (MESSAGE_TYPE_SYSTEM, "System"),
    ]

    SYSTEM_REQUEST_SENT = "REQUEST_SENT"
    SYSTEM_REQUEST_APPROVED = "REQUEST_APPROVED"
    SYSTEM_PAYMENT_MADE = "PAYMENT_MADE"
    SYSTEM_TOOL_PICKED_UP = "TOOL_PICKED_UP"
    SYSTEM_BOOKING_CANCELLED = "BOOKING_CANCELLED"
    SYSTEM_BOOKING_COMPLETED = "BOOKING_COMPLETED"

    SYSTEM_KIND_CHOICES = [
        (SYSTEM_REQUEST_SENT, "Request sent"),
        (SYSTEM_REQUEST_APPROVED, "Request approved"),
        (SYSTEM_PAYMENT_MADE, "Payment made"),
        (SYSTEM_TOOL_PICKED_UP, "Tool picked up"),
        (SYSTEM_BOOKING_CANCELLED, "Booking cancelled"),
        (SYSTEM_BOOKING_COMPLETED, "Booking completed"),
    ]

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="chat_messages",
    )
    message_type = models.CharField(
        max_length=10,
        choices=MESSAGE_TYPE_CHOICES,
        default=MESSAGE_TYPE_USER,
    )
    system_kind = models.CharField(
        max_length=32,
        choices=SYSTEM_KIND_CHOICES,
        null=True,
        blank=True,
    )
    text = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["created_at"]
        db_table = "bookings_message"

    def __str__(self) -> str:
        return (
            "Message("
            f"conv={self.conversation_id}, "
            f"type={self.message_type}, "
            f"system={self.system_kind}"
            ")"
        )


class ConversationReadState(models.Model):
    """Track the last read message per user in a conversation."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="read_states",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conversation_read_states",
    )
    last_read_message = models.ForeignKey(
        "chat.Message",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    last_read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ("conversation", "user")

    def __str__(self) -> str:  # pragma: no cover - simple repr
        return f"ReadState(conv={self.conversation_id}, user={self.user_id})"


def get_or_create_booking_conversation(booking: "Booking") -> Conversation:
    """Return the booking's conversation, creating it on first access."""
    conv, _ = Conversation.objects.get_or_create(
        booking=booking,
        defaults={
            "owner": booking.owner,
            "renter": booking.renter,
        },
    )
    return conv


def _push_chat_event_for_conversation(conv: Conversation, msg: Message) -> None:
    """Send a Redis event to both owner and renter when a message is created."""
    payload = {
        "conversation_id": conv.id,
        "booking_id": conv.booking_id,
        "message": {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "message_type": msg.message_type,
            "system_kind": msg.system_kind,
            "text": msg.text,
            "created_at": msg.created_at.isoformat(),
        },
    }
    push_event(conv.owner_id, "chat:new_message", payload)
    push_event(conv.renter_id, "chat:new_message", payload)


def create_system_message(
    booking: "Booking",
    system_kind: str,
    text: str,
    *,
    close_chat: bool = False,
) -> Tuple[Conversation, Message]:
    """Create a system-generated chat entry for the booking."""
    conv = get_or_create_booking_conversation(booking)
    if close_chat and conv.is_active:
        conv.is_active = False
        conv.save(update_fields=["is_active"])
    msg = Message.objects.create(
        conversation=conv,
        sender=None,
        message_type=Message.MESSAGE_TYPE_SYSTEM,
        system_kind=system_kind,
        text=text,
    )
    _push_chat_event_for_conversation(conv, msg)
    return conv, msg


def create_user_message(
    conversation: Conversation,
    sender: "User",
    text: str,
) -> Message:
    """Create a user-authored chat message and emit events."""
    msg = Message.objects.create(
        conversation=conversation,
        sender=sender,
        message_type=Message.MESSAGE_TYPE_USER,
        text=text,
    )
    _push_chat_event_for_conversation(conversation, msg)
    return msg


def mark_conversation_read(
    conversation: Conversation, user: "User"
) -> ConversationReadState | None:
    """Mark the conversation as read for the given user."""
    if not user or user.id not in {conversation.owner_id, conversation.renter_id}:
        return None

    last_message = conversation.messages.order_by("-id").first()
    state, _ = ConversationReadState.objects.get_or_create(
        conversation=conversation,
        user=user,
        defaults={"last_read_at": timezone.now(), "last_read_message": last_message},
    )
    if last_message and state.last_read_message_id == last_message.id:
        return state

    if last_message:
        state.last_read_message = last_message
        state.last_read_at = timezone.now()
        state.save(update_fields=["last_read_message", "last_read_at"])
    elif not state.last_read_at:
        state.last_read_at = timezone.now()
        state.save(update_fields=["last_read_at"])
    return state


def get_unread_message_count(conversation: Conversation, user: "User") -> int:
    """Return unread message count for the user in the conversation."""
    if not user or user.id not in {conversation.owner_id, conversation.renter_id}:
        return 0
    state = getattr(conversation, "_read_state", None)
    if state is None:
        try:
            state = conversation.read_states.get(user=user)
        except ConversationReadState.DoesNotExist:
            state = None
    last_read_id = state.last_read_message_id if state else None

    qs = conversation.messages.exclude(sender=user)
    if last_read_id:
        qs = qs.filter(id__gt=last_read_id)
    return qs.count()
