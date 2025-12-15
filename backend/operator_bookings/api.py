from django.db.models import Prefetch
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics

from bookings.models import Booking
from operator_bookings.filters import OperatorBookingFilter
from operator_bookings.models import BookingEvent
from operator_bookings.serializers import (
    OperatorBookingDetailSerializer,
    OperatorBookingListSerializer,
)
from operator_core.permissions import HasOperatorRole, IsOperator

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)


class OperatorBookingListView(generics.ListAPIView):
    serializer_class = OperatorBookingListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorBookingFilter
    http_method_names = ["get"]

    def get_queryset(self):
        return (
            Booking.objects.select_related("listing", "owner", "renter")
            .filter(listing__is_deleted=False)
            .order_by("-created_at")
        )


class OperatorBookingDetailView(generics.RetrieveAPIView):
    serializer_class = OperatorBookingDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    lookup_field = "pk"
    http_method_names = ["get"]

    def get_queryset(self):
        events_qs = BookingEvent.objects.select_related("actor").order_by("created_at", "id")
        return (
            Booking.objects.select_related("listing", "owner", "renter")
            .filter(listing__is_deleted=False)
            .prefetch_related(
                Prefetch("events", queryset=events_qs, to_attr="prefetched_events"),
                Prefetch("dispute_cases", to_attr="prefetched_disputes"),
            )
        )
