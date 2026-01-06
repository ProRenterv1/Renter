from __future__ import annotations

import django_filters as filters
from django.db.models import Q

from operator_core.models import OperatorAuditEvent


class OperatorAuditEventFilter(filters.FilterSet):
    actor_id = filters.NumberFilter(field_name="actor_id")
    actor = filters.CharFilter(method="filter_actor")
    entity_type = filters.CharFilter(field_name="entity_type", lookup_expr="iexact")
    action = filters.CharFilter(method="filter_action")
    created_at_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = OperatorAuditEvent
        fields = [
            "actor_id",
            "entity_type",
            "action",
        ]

    def filter_actor(self, queryset, name, value):
        if not value:
            return queryset
        search = value.strip()
        if not search:
            return queryset
        return queryset.filter(
            Q(actor__email__icontains=search)
            | Q(actor__username__icontains=search)
            | Q(actor__first_name__icontains=search)
            | Q(actor__last_name__icontains=search)
        )

    def filter_action(self, queryset, name, value):
        if not value:
            return queryset
        search = value.strip()
        if not search:
            return queryset
        if "*" in search:
            search = search.replace("*", "")
        return queryset.filter(action__icontains=search)
