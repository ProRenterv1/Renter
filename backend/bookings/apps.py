"""App configuration for the bookings domain."""

from django.apps import AppConfig


class BookingsConfig(AppConfig):
    """Register the bookings app with sane defaults."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "bookings"

    def ready(self) -> None:
        """Load auxiliary models that live outside bookings.models."""
        try:
            import chat_models  # noqa: F401
        except ModuleNotFoundError:
            # Chat feature not installed in some environments.
            pass
