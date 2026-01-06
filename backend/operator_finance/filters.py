import django_filters as filters
from django.db.models import Q

from payments.models import Transaction


class OperatorTransactionFilter(filters.FilterSet):
    kind = filters.CharFilter(field_name="kind", lookup_expr="iexact")
    booking = filters.NumberFilter(field_name="booking_id")
    user = filters.CharFilter(method="filter_user")
    created_at_after = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_at_before = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Transaction
        fields = ["kind", "booking", "user"]

    def filter_user(self, queryset, name, value):
        if value is None:
            return queryset
        value = str(value).strip()
        if not value:
            return queryset

        if value.isdigit():
            return queryset.filter(user_id=int(value))

        tokens = [token for token in value.split() if token]
        if not tokens:
            return queryset

        query = Q()
        for token in tokens:
            token_q = (
                Q(user__email__icontains=token)
                | Q(user__first_name__icontains=token)
                | Q(user__last_name__icontains=token)
                | Q(user__username__icontains=token)
            )
            query &= token_q

        return queryset.filter(query)
