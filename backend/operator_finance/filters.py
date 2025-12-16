import django_filters

from payments.models import Transaction


class OperatorTransactionFilter(django_filters.FilterSet):
    user_id = django_filters.NumberFilter(field_name="user_id")
    booking_id = django_filters.NumberFilter(field_name="booking_id")
    kind = django_filters.CharFilter(field_name="kind")
    stripe_id = django_filters.CharFilter(field_name="stripe_id", lookup_expr="icontains")
    created_from = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    created_to = django_filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = Transaction
        fields = ["user_id", "booking_id", "kind", "stripe_id"]
