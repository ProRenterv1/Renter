from __future__ import annotations

import django_filters as filters

from promotions.models import PromotedSlot


class OperatorPromotionFilter(filters.FilterSet):
    active = filters.BooleanFilter(field_name="active")
    owner_id = filters.NumberFilter(field_name="owner_id")
    listing_id = filters.NumberFilter(field_name="listing_id")
    starts_at_after = filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="gte")
    starts_at_before = filters.IsoDateTimeFilter(field_name="starts_at", lookup_expr="lte")
    ends_at_after = filters.IsoDateTimeFilter(field_name="ends_at", lookup_expr="gte")
    ends_at_before = filters.IsoDateTimeFilter(field_name="ends_at", lookup_expr="lte")
    created_at_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = PromotedSlot
        fields = [
            "active",
            "owner_id",
            "listing_id",
        ]
