import django_filters as filters
from django.utils import timezone

from bookings.models import Booking


class OperatorBookingFilter(filters.FilterSet):
    status = filters.CharFilter(field_name="status", lookup_expr="iexact")
    created_at_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    owner = filters.NumberFilter(field_name="owner_id")
    renter = filters.NumberFilter(field_name="renter_id")
    overdue = filters.BooleanFilter(method="filter_overdue")

    class Meta:
        model = Booking
        fields = ["status", "owner", "renter", "overdue"]

    def filter_overdue(self, queryset, name, value):
        if value is None:
            return queryset

        today = timezone.localdate()
        overdue_q = {
            "end_date__lt": today,
            "return_confirmed_at__isnull": True,
        }
        if value:
            return queryset.filter(**overdue_q)
        return queryset.exclude(**overdue_q)
