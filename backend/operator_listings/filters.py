import django_filters as filters
from django.contrib.contenttypes.models import ContentType

from listings.models import Listing
from operator_core.models import OperatorNote


class OperatorListingFilter(filters.FilterSet):
    owner = filters.NumberFilter(field_name="owner_id")
    city = filters.CharFilter(field_name="city", lookup_expr="icontains")
    category = filters.CharFilter(field_name="category__slug", lookup_expr="iexact")
    is_active = filters.BooleanFilter(field_name="is_active")
    needs_review = filters.BooleanFilter(method="filter_needs_review")
    created_at_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Listing
        fields = [
            "owner",
            "city",
            "category",
            "is_active",
            "needs_review",
        ]

    def filter_needs_review(self, queryset, name, value):
        if value is None:
            return queryset
        content_type = ContentType.objects.get_for_model(Listing)
        tagged_ids = (
            OperatorNote.objects.filter(
                content_type=content_type,
                tags__name="needs_review",
            )
            .values_list("object_id", flat=True)
            .distinct()
        )
        if value:
            return queryset.filter(pk__in=tagged_ids)
        return queryset.exclude(pk__in=tagged_ids)
