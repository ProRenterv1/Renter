from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import QueryDict

FEED_VERSION_KEY = "listings:feed:version"
FEED_CACHE_PREFIX = "listings:feed"
CATEGORIES_CACHE_KEY = "listings:categories:v1"


def _get_feed_version() -> int:
    version = cache.get(FEED_VERSION_KEY)
    if version is None:
        cache.add(FEED_VERSION_KEY, 1)
        return 1
    try:
        return int(version)
    except (TypeError, ValueError):
        return 1


def _bump_feed_version() -> None:
    try:
        cache.incr(FEED_VERSION_KEY)
    except Exception:
        cache.set(FEED_VERSION_KEY, _get_feed_version() + 1, timeout=None)


def normalize_query_params(params: QueryDict) -> str:
    items: list[tuple[str, str]] = []
    for key in sorted(params.keys()):
        for value in params.getlist(key):
            items.append((key, value))
    return urlencode(items)


def listing_feed_cache_key(params: QueryDict, *, variant: str = "full") -> str:
    normalized = normalize_query_params(params)
    safe_variant = (variant or "full").replace(":", "_")
    return f"{FEED_CACHE_PREFIX}:{safe_variant}:v{_get_feed_version()}:{normalized or 'all'}"


def invalidate_listing_feed_cache() -> None:
    _bump_feed_version()


def get_categories_cache_key() -> str:
    return CATEGORIES_CACHE_KEY


def invalidate_categories_cache() -> None:
    cache.delete(CATEGORIES_CACHE_KEY)


def listings_cache_timeout() -> int:
    return getattr(settings, "CACHE_TTL_LISTINGS", 120)


def categories_cache_timeout() -> int:
    return getattr(settings, "CACHE_TTL_CATEGORIES", 300)
