from __future__ import annotations

from typing import Set

from django.conf import settings
from django.core.cache import cache

PROMOTED_FEED_IDS_CACHE_KEY = "promotions:active_feed_listing_ids"


def get_active_promoted_listing_ids(now=None) -> Set[int]:
    cached = cache.get(PROMOTED_FEED_IDS_CACHE_KEY)
    if cached is not None:
        try:
            return {int(value) for value in cached}
        except Exception:
            return set()

    from .models import PromotedSlot

    ids = list(PromotedSlot.active_for_feed(now=now).values_list("listing_id", flat=True))
    cache.set(
        PROMOTED_FEED_IDS_CACHE_KEY,
        ids,
        timeout=getattr(settings, "CACHE_TTL_PROMOTIONS", 60),
    )
    return set(ids)


def invalidate_active_promoted_listing_ids_cache() -> None:
    cache.delete(PROMOTED_FEED_IDS_CACHE_KEY)
