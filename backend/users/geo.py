from __future__ import annotations

import ipaddress
from typing import Optional

import requests
from django.conf import settings
from django.core.cache import cache

__all__ = ["get_location_for_ip"]

_CACHE_PREFIX = "ip_geo:"
_CACHE_SENTINEL = object()


def get_location_for_ip(ip: Optional[str]) -> Optional[str]:
    """
    Return a human-friendly location for the supplied IP address.

    * Internal/reserved addresses resolve to IP_GEO_PRIVATE_LABEL.
    * Public addresses hit an external API when IP_GEO_LOOKUP_ENABLED is True.
    * Responses are cached via Django's cache backend to avoid hammering the API.
    """
    if not ip:
        return None

    if _is_internal_ip(ip):
        return getattr(settings, "IP_GEO_PRIVATE_LABEL", "Local network")

    if not getattr(settings, "IP_GEO_LOOKUP_ENABLED", False):
        return None

    cache_key = f"{_CACHE_PREFIX}{ip}"
    cached = cache.get(cache_key, _CACHE_SENTINEL)
    if cached is not _CACHE_SENTINEL:
        return cached or None

    location = _fetch_location(ip)
    ttl = max(60, int(getattr(settings, "IP_GEO_CACHE_TTL", 3600) or 3600))
    cache.set(cache_key, location or "", ttl)
    return location


def _is_internal_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        return True

    return not ip_obj.is_global


def _fetch_location(ip: str) -> Optional[str]:
    url_template = getattr(settings, "IP_GEO_LOOKUP_URL", "https://ipapi.co/{ip}/json/")
    url = url_template.format(ip=ip)
    timeout = float(getattr(settings, "IP_GEO_LOOKUP_TIMEOUT", 1.5))

    headers = {
        "Accept": "application/json",
        "User-Agent": "Renter-IP-Geolocation/1.0",
    }

    params = None
    token = getattr(settings, "IP_GEO_LOOKUP_TOKEN", None)
    if token:
        param_name = getattr(settings, "IP_GEO_LOOKUP_TOKEN_PARAM", "key")
        params = {param_name: token}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException:
        return None

    try:
        payload = response.json()
    except ValueError:
        return None

    if isinstance(payload, dict):
        if payload.get("error"):
            return None
        return _compose_label(payload)
    return None


def _compose_label(payload: dict) -> Optional[str]:
    def _first_nonempty(*keys):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    return stripped
        return None

    components: list[str] = []
    for part in (
        _first_nonempty("city", "town"),
        _first_nonempty("region", "region_name", "state"),
        _first_nonempty("country_name", "country"),
    ):
        if part and part not in components:
            components.append(part)

    return ", ".join(components) if components else None
