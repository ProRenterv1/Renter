from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from threading import Lock
from typing import Any


_CACHE_TTL_SECONDS = 5.0
_MISSING = object()


@dataclass(frozen=True)
class _CacheEntry:
    expires_at: float
    value: object


_cache: dict[str, _CacheEntry] = {}
_cache_lock = Lock()


def clear_settings_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _clone_if_mutable(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return copy.deepcopy(value)
    return value


def _cache_get(key: str, now: float) -> object | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if now >= entry.expires_at:
            _cache.pop(key, None)
            return None
        return entry.value


def _cache_set(key: str, now: float, value: object) -> None:
    with _cache_lock:
        _cache[key] = _CacheEntry(expires_at=now + _CACHE_TTL_SECONDS, value=value)


def get_setting(key: str, default: Any) -> Any:
    """
    Resolve a setting value from operator_settings.DbSetting with effective_at support.

    Selection rules:
    - key matches exactly
    - effective_at is NULL or <= timezone.now()
    - order by effective_at DESC NULLS LAST, then updated_at DESC

    Safety:
    - If the app is not installed, migrations aren't applied, or DB is unavailable,
      return default without raising.
    - Uses a 5s in-process TTL cache (misses included).
    """

    now_mono = time.monotonic()
    cached = _cache_get(key, now_mono)
    if cached is not None:
        return default if cached is _MISSING else _clone_if_mutable(cached)

    value: object = _MISSING
    try:
        from django.apps import apps as django_apps

        if not django_apps.ready or not django_apps.is_installed("operator_settings"):
            value = _MISSING
        else:
            DbSetting = django_apps.get_model("operator_settings", "DbSetting")
            from django.db.models import F, Q
            from django.utils import timezone

            now = timezone.now()
            value = (
                DbSetting.objects.filter(key=key)
                .filter(Q(effective_at__isnull=True) | Q(effective_at__lte=now))
                .order_by(F("effective_at").desc(nulls_last=True), "-updated_at")
                .values_list("value_json", flat=True)
                .first()
            )
            if value is None:
                value = _MISSING
    except Exception:
        value = _MISSING

    _cache_set(key, now_mono, value)
    return default if value is _MISSING else _clone_if_mutable(value)


def get_bool(key: str, default: bool = False) -> bool:
    value = get_setting(key, default)
    return value if type(value) is bool else default


def get_int(key: str, default: int = 0) -> int:
    value = get_setting(key, default)
    return value if type(value) is int else default


def get_decimal(key: str, default: Decimal = Decimal("0")) -> Decimal:
    value = get_setting(key, default)
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value)
        except (InvalidOperation, ValueError):
            return default
    return default


def get_str(key: str, default: str = "") -> str:
    value = get_setting(key, default)
    return value if isinstance(value, str) else default


def get_json(key: str, default: Any | None = None) -> Any:
    if default is None:
        default = {}
    value = get_setting(key, default)
    return value if isinstance(value, (dict, list)) else default

