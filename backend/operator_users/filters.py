import django_filters as filters
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class OperatorUserFilter(filters.FilterSet):
    email = filters.CharFilter(field_name="email", lookup_expr="icontains")
    name = filters.CharFilter(method="filter_name")
    phone = filters.CharFilter(field_name="phone", lookup_expr="icontains")
    city = filters.CharFilter(field_name="city", lookup_expr="icontains")
    can_rent = filters.BooleanFilter(field_name="can_rent")
    can_list = filters.BooleanFilter(field_name="can_list")
    is_active = filters.BooleanFilter(field_name="is_active")
    email_verified = filters.BooleanFilter(field_name="email_verified")
    phone_verified = filters.BooleanFilter(field_name="phone_verified")
    identity_verified = filters.BooleanFilter(method="filter_identity_verified")
    date_joined_after = filters.IsoDateTimeFilter(field_name="date_joined", lookup_expr="gte")
    date_joined_before = filters.IsoDateTimeFilter(field_name="date_joined", lookup_expr="lte")

    class Meta:
        model = User
        fields = [
            "email",
            "name",
            "phone",
            "city",
            "can_rent",
            "can_list",
            "is_active",
            "email_verified",
            "phone_verified",
            "identity_verified",
        ]

    def filter_name(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(first_name__icontains=value)
            | Q(last_name__icontains=value)
            | Q(username__icontains=value)
            | Q(email__icontains=value)
        )

    def filter_identity_verified(self, queryset, name, value):
        if value is None:
            return queryset
        return queryset.filter(payout_account__is_fully_onboarded=value)
