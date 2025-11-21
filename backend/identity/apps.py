"""Application configuration for the identity app."""

from django.apps import AppConfig


class IdentityConfig(AppConfig):
    """Register the identity app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "identity"
