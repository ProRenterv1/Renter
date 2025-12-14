from django.contrib.auth import get_user_model
from django.db.models import (
    BooleanField,
    Count,
    ExpressionWrapper,
    F,
    IntegerField,
    Prefetch,
    Value,
)
from django.db.models.functions import Coalesce
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import generics

from bookings.models import Booking
from operator_core.permissions import HasOperatorRole, IsOperator
from operator_users.filters import OperatorUserFilter
from operator_users.serializers import OperatorUserDetailSerializer, OperatorUserListSerializer

User = get_user_model()

ALLOWED_OPERATOR_ROLES = (
    "operator_support",
    "operator_moderator",
    "operator_finance",
    "operator_admin",
)

ZERO_INT = Value(0, output_field=IntegerField())


def _annotated_staff_queryset():
    return (
        User.objects.all()
        .annotate(
            listings_count=Count("listings", distinct=True),
            bookings_as_renter_count=Count("bookings_as_renter", distinct=True),
            bookings_as_owner_count=Count("bookings_as_owner", distinct=True),
            disputes_as_owner_count=Count("bookings_as_owner__dispute_cases", distinct=True),
            disputes_as_renter_count=Count("bookings_as_renter__dispute_cases", distinct=True),
        )
        .annotate(
            disputes_count=ExpressionWrapper(
                Coalesce(F("disputes_as_owner_count"), ZERO_INT)
                + Coalesce(F("disputes_as_renter_count"), ZERO_INT),
                output_field=IntegerField(),
            )
        )
        .annotate(
            identity_verified=Coalesce(
                F("payout_account__is_fully_onboarded"),
                Value(False),
                output_field=BooleanField(),
            )
        )
    )


class OperatorUserListView(generics.ListAPIView):
    serializer_class = OperatorUserListSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OperatorUserFilter
    http_method_names = ["get"]

    def get_queryset(self):
        qs = _annotated_staff_queryset()

        ordering = (self.request.query_params.get("ordering") or "newest").strip()

        if ordering == "most_bookings":
            qs = qs.annotate(
                total_bookings_count=ExpressionWrapper(
                    Coalesce(F("bookings_as_owner_count"), ZERO_INT)
                    + Coalesce(F("bookings_as_renter_count"), ZERO_INT),
                    output_field=IntegerField(),
                )
            ).order_by("-total_bookings_count", "-date_joined")
        elif ordering == "most_disputes":
            qs = qs.order_by("-disputes_count", "-date_joined")
        else:
            qs = qs.order_by("-date_joined")

        return qs


class OperatorUserDetailView(generics.RetrieveAPIView):
    serializer_class = OperatorUserDetailSerializer
    permission_classes = [IsOperator, HasOperatorRole.with_roles(ALLOWED_OPERATOR_ROLES)]
    http_method_names = ["get"]
    lookup_field = "pk"

    def get_queryset(self):
        recent_bookings_qs = Booking.objects.select_related(
            "listing", "listing__owner", "owner", "renter"
        ).order_by("-created_at")
        return _annotated_staff_queryset().prefetch_related(
            Prefetch("bookings_as_owner", queryset=recent_bookings_qs),
            Prefetch("bookings_as_renter", queryset=recent_bookings_qs),
        )
