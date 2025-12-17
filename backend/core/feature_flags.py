from __future__ import annotations

from typing import Any, Dict


def flag_enabled(key: str, default: bool = False) -> bool:
    """
    Return FeatureFlag.enabled for a given key, or default if missing/unsafe to query.
    """

    try:
        from django.apps import apps as django_apps

        if not django_apps.ready or not django_apps.is_installed("operator_settings"):
            return default

        FeatureFlag = django_apps.get_model("operator_settings", "FeatureFlag")
        enabled = FeatureFlag.objects.filter(key=key).values_list("enabled", flat=True).first()
        if enabled is None:
            return default
        return bool(enabled)
    except Exception:
        return default


def get_maintenance_banner() -> Dict[str, Any]:
    """
    Returns the current MaintenanceBanner as a simple dict:
    {"enabled": bool, "severity": "...", "message": "...", "updated_at": ...}

    If DB is unavailable or no rows exist, returns a disabled default banner.
    """

    default_banner: Dict[str, Any] = {
        "enabled": False,
        "severity": "info",
        "message": "",
        "updated_at": None,
    }

    try:
        from django.apps import apps as django_apps

        if not django_apps.ready or not django_apps.is_installed("operator_settings"):
            return default_banner

        MaintenanceBanner = django_apps.get_model("operator_settings", "MaintenanceBanner")
        row = (
            MaintenanceBanner.objects.order_by("-updated_at", "-id")
            .values("enabled", "severity", "message", "updated_at")
            .first()
        )
        if not row:
            return default_banner

        severity = row.get("severity") or "info"
        if severity not in {"info", "warning", "error"}:
            severity = "info"

        return {
            "enabled": bool(row.get("enabled", False)),
            "severity": severity,
            "message": row.get("message") or "",
            "updated_at": row.get("updated_at"),
        }
    except Exception:
        return default_banner
