from __future__ import annotations

from datetime import timedelta

import django_filters as filters
from django.utils import timezone

from disputes.models import DisputeCase

DUE_SOON_HOURS = 48


class OperatorDisputeFilter(filters.FilterSet):
    status = filters.CharFilter(field_name="status")
    category = filters.CharFilter(field_name="category")
    damage_flow_kind = filters.CharFilter(field_name="damage_flow_kind")
    flow = filters.CharFilter(method="filter_flow")
    stage = filters.CharFilter(method="filter_stage")
    evidence_missing = filters.BooleanFilter(method="filter_evidence_missing")
    safety_flag = filters.BooleanFilter(method="filter_safety_flag")
    suspend_flag = filters.BooleanFilter(method="filter_suspend_flag")
    is_safety_incident = filters.BooleanFilter(field_name="is_safety_incident")
    requires_listing_suspend = filters.BooleanFilter(field_name="requires_listing_suspend")
    owner_email = filters.CharFilter(method="filter_owner_email")
    renter_email = filters.CharFilter(method="filter_renter_email")
    booking_id = filters.NumberFilter(field_name="booking_id")
    created_at_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    rebuttal_due_soon = filters.BooleanFilter(method="filter_rebuttal_due_soon")
    rebuttal_overdue = filters.BooleanFilter(method="filter_rebuttal_overdue")
    intake_due_soon = filters.BooleanFilter(method="filter_intake_due_soon")
    intake_overdue = filters.BooleanFilter(method="filter_intake_overdue")

    class Meta:
        model = DisputeCase
        fields = [
            "status",
            "category",
            "damage_flow_kind",
            "flow",
            "stage",
            "evidence_missing",
            "safety_flag",
            "suspend_flag",
            "owner_email",
            "renter_email",
            "is_safety_incident",
            "requires_listing_suspend",
            "booking_id",
        ]

    def _due_window(self):
        now = timezone.now()
        soon = now + timedelta(hours=DUE_SOON_HOURS)
        return now, soon

    def filter_rebuttal_due_soon(self, queryset, name, value):
        if not value:
            return queryset
        now, soon = self._due_window()
        return queryset.filter(
            status=DisputeCase.Status.AWAITING_REBUTTAL,
            rebuttal_due_at__isnull=False,
            rebuttal_due_at__gt=now,
            rebuttal_due_at__lte=soon,
        )

    def filter_rebuttal_overdue(self, queryset, name, value):
        if not value:
            return queryset
        now = timezone.now()
        return queryset.filter(
            status=DisputeCase.Status.AWAITING_REBUTTAL,
            rebuttal_due_at__isnull=False,
            rebuttal_due_at__lt=now,
        )

    def filter_intake_due_soon(self, queryset, name, value):
        if not value:
            return queryset
        now, soon = self._due_window()
        return queryset.filter(
            status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            intake_evidence_due_at__isnull=False,
            intake_evidence_due_at__gt=now,
            intake_evidence_due_at__lte=soon,
        )

    def filter_intake_overdue(self, queryset, name, value):
        if not value:
            return queryset
        now = timezone.now()
        return queryset.filter(
            status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
            intake_evidence_due_at__isnull=False,
            intake_evidence_due_at__lt=now,
        )

    def filter_flow(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(damage_flow_kind=value)

    def filter_stage(self, queryset, name, value):
        if not value:
            return queryset
        normalized = value.strip().lower()
        if normalized == "intake":
            return queryset.filter(
                status__in=[
                    DisputeCase.Status.OPEN,
                    DisputeCase.Status.INTAKE_MISSING_EVIDENCE,
                ]
            )
        if normalized == "awaiting_rebuttal":
            return queryset.filter(status=DisputeCase.Status.AWAITING_REBUTTAL)
        if normalized == "under_review":
            return queryset.filter(status=DisputeCase.Status.UNDER_REVIEW)
        if normalized == "resolved":
            return queryset.filter(
                status__in=[
                    DisputeCase.Status.RESOLVED_RENTER,
                    DisputeCase.Status.RESOLVED_OWNER,
                    DisputeCase.Status.RESOLVED_PARTIAL,
                    DisputeCase.Status.CLOSED_AUTO,
                ]
            )
        return queryset.filter(status=normalized)

    def filter_evidence_missing(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(status=DisputeCase.Status.INTAKE_MISSING_EVIDENCE)

    def filter_safety_flag(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(is_safety_incident=True)

    def filter_suspend_flag(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(requires_listing_suspend=True)

    def filter_owner_email(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(booking__owner__email__icontains=value)

    def filter_renter_email(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(booking__renter__email__icontains=value)
