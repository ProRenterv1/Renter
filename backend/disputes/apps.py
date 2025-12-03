"""Application configuration for disputes."""

from django.apps import AppConfig


class DisputesConfig(AppConfig):
    """Register the disputes app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "disputes"
