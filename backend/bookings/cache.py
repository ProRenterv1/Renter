from __future__ import annotations

from typing import Iterable, Set
from urllib.parse import urlencode

from django.conf import settings
from django.core.cache import cache
from django.http import QueryDict

BOOKINGS_CACHE_VERSION_KEY = "bookings:my:version:{user_id}"


def _get_version(user_id: int) -> int:
    key = BOOKINGS_CACHE_VERSION_KEY.format(user_id=user_id)
    version = cache.get(key)
    if version is None:
        cache.add(key, 1)
        return 1
    try:
        return int(version)
    except (TypeError, ValueError):
        return 1


def _bump_version(user_id: int) -> None:
    key = BOOKINGS_CACHE_VERSION_KEY.format(user_id=user_id)
    try:
        cache.incr(key)
    except Exception:
        cache.set(key, _get_version(user_id) + 1, timeout=None)


def _normalize_query_params(params: QueryDict) -> str:
    items: list[tuple[str, str]] = []
    for key in sorted(params.keys()):
        for value in params.getlist(key):
            items.append((key, value))
    return urlencode(items)


def bookings_cache_key(user_id: int, params: QueryDict) -> str:
    normalized = _normalize_query_params(params)
    return f"bookings:my:u{user_id}:v{_get_version(user_id)}:{normalized or 'all'}"


def invalidate_bookings_cache_for_users(user_ids: Iterable[int | None]) -> None:
    unique_ids: Set[int] = set()
    for user_id in user_ids:
        if user_id:
            unique_ids.add(int(user_id))
    for user_id in unique_ids:
        _bump_version(user_id)


def bookings_cache_timeout() -> int:
    return getattr(settings, "CACHE_TTL_RECENT_RENTALS", 120)
