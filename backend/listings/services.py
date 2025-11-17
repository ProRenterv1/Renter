from django.db.models import Q, QuerySet

from .models import Listing


def search_listings(
    qs: QuerySet[Listing],
    q: str | None,
    price_min: float | None,
    price_max: float | None,
    category: str | None = None,
    city: str | None = None,
    owner_id: int | None = None,
) -> QuerySet[Listing]:
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(city__icontains=q))
    if price_min is not None:
        qs = qs.filter(daily_price_cad__gte=price_min)
    if price_max is not None:
        qs = qs.filter(daily_price_cad__lte=price_max)
    if category:
        qs = qs.filter(category__slug=category)
    if city:
        qs = qs.filter(city__iexact=city)
    if owner_id is not None:
        qs = qs.filter(owner_id=owner_id)
    return qs.filter(is_active=True, is_available=True).order_by("-created_at")
