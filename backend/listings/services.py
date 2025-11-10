from django.db.models import Q, QuerySet

from .models import Listing


def search_listings(
    qs: QuerySet[Listing],
    q: str | None,
    price_min: float | None,
    price_max: float | None,
) -> QuerySet[Listing]:
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(city__icontains=q))
    if price_min is not None:
        qs = qs.filter(daily_price_cad__gte=price_min)
    if price_max is not None:
        qs = qs.filter(daily_price_cad__lte=price_max)
    return qs.filter(is_active=True).order_by("-created_at")
