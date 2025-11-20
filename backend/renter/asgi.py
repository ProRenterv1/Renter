import os
from typing import Any, Awaitable, Callable

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "renter.settings.dev")

from django.core.asgi import get_asgi_application  # noqa: E402

django_asgi_app = get_asgi_application()

from core.ws_events import events_ws_app  # noqa: E402


async def application(scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
    """
    Route HTTP traffic to Django and /ws/events/ WebSockets to the event streamer.
    """
    if scope.get("type") == "websocket" and scope.get("path", "").startswith("/ws/events"):
        await events_ws_app(scope, receive, send)
        return

    await django_asgi_app(scope, receive, send)
