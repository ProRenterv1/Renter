from django.db.models import Max, Prefetch
from rest_framework import generics

from chat.models import Conversation, Message
from operator_comms.serializers import (
    OperatorConversationDetailSerializer,
    OperatorConversationListSerializer,
)
from operator_core.permissions import HasOperatorRole, IsOperator

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


class OperatorConversationListView(generics.ListAPIView):
    serializer_class = OperatorConversationListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["get"]

    def get_queryset(self):
        return (
            Conversation.objects.select_related(
                "booking",
                "booking__listing",
                "listing",
                "owner",
                "renter",
            )
            .annotate(last_message_at=Max("messages__created_at"))
            .order_by("-last_message_at", "-created_at")
        )


class OperatorConversationDetailView(generics.RetrieveAPIView):
    serializer_class = OperatorConversationDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    lookup_field = "pk"
    http_method_names = ["get"]

    def get_queryset(self):
        messages_qs = Message.objects.select_related("sender").order_by("created_at")
        return (
            Conversation.objects.select_related(
                "booking",
                "booking__listing",
                "listing",
                "owner",
                "renter",
            )
            .annotate(last_message_at=Max("messages__created_at"))
            .prefetch_related(
                Prefetch("messages", queryset=messages_qs, to_attr="prefetched_messages")
            )
        )
