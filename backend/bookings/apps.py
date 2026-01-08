"""App configuration for the bookings domain."""

from django.apps import AppConfig


class BookingsConfig(AppConfig):
    """Register the bookings app with sane defaults."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "bookings"

    def ready(self):
        # Import signal handlers
        from . import signals  # noqa: F401
