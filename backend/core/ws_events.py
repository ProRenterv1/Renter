"""ASGI WebSocket app that streams Redis events to authenticated users."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Dict
from urllib.parse import parse_qs

from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken

from core.redis import read_user_events

logger = logging.getLogger(__name__)

DEFAULT_BLOCK_MS = 25_000
DEFAULT_COUNT = 100

_read_events_async = sync_to_async(read_user_events, thread_sensitive=False)


class AuthenticationError(Exception):
    """Raised when the access token is missing or invalid."""


def _extract_token(scope: Dict[str, Any]) -> str:
    """Return the ?token=... query parameter from the ASGI scope."""
    query_string = scope.get("query_string", b"")
    if isinstance(query_string, bytes):
        raw_query = query_string.decode("utf-8", errors="ignore")
    else:
        raw_query = str(query_string)
    params = parse_qs(raw_query, keep_blank_values=True)
    values = params.get("token")
    return values[0] if values else ""


async def _authenticate_user(scope: Dict[str, Any]) -> Any:
    """Validate the JWT access token and return the associated user."""
    token = _extract_token(scope).strip()
    if not token:
        raise AuthenticationError("Missing token")

    try:
        access = AccessToken(token)
    except TokenError as exc:
        raise AuthenticationError("Invalid token") from exc

    user_id_value = access.get("user_id")
    try:
        user_id = int(user_id_value)
    except (TypeError, ValueError):
        raise AuthenticationError("Token missing user_id claim")

    user_model = get_user_model()
    try:
        return await sync_to_async(user_model.objects.get, thread_sensitive=True)(pk=user_id)
    except user_model.DoesNotExist as exc:
        raise AuthenticationError("User does not exist") from exc


async def _send_close(send, code: int) -> None:
    """Best-effort close helper that tolerates already closed sockets."""
    message = {"type": "websocket.close", "code": code}
    try:
        await send(message)
    except Exception:  # pragma: no cover - defensive, depends on server implementation
        logger.debug("events_ws: failed to send close frame code=%s", code, exc_info=True)


async def _stream_events(user_id: int, send, stop_event: asyncio.Event) -> None:
    """Background producer task pulling Redis events and pushing WebSocket frames."""
    cursor = "$"
    try:
        while not stop_event.is_set():
            next_cursor, events = await _read_events_async(
                user_id=user_id,
                cursor=cursor,
                block_ms=DEFAULT_BLOCK_MS,
                count=DEFAULT_COUNT,
            )
            if next_cursor:
                cursor = next_cursor
            if events:
                payload = json.dumps(
                    {
                        "cursor": cursor,
                        "events": events,
                    },
                    separators=(",", ":"),
                )
                await send({"type": "websocket.send", "text": payload})
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("events_ws: sender loop failed for user=%s", user_id)
        stop_event.set()
        await _send_close(send, 1011)


async def _receive_loop(receive, stop_event: asyncio.Event) -> None:
    """Consume client messages until disconnect."""
    try:
        while not stop_event.is_set():
            message = await receive()
            msg_type = message.get("type")
            if msg_type == "websocket.disconnect":
                stop_event.set()
                break
            if msg_type == "websocket.receive":
                # Ignore client messages for now; reserved for future ping/pong support.
                continue
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("events_ws: receiver loop failed")
        stop_event.set()


async def events_ws_app(scope: Dict[str, Any], receive, send) -> None:
    """
    WebSocket ASGI app that authenticates via JWT and streams Redis events.
    """
    if scope.get("type") != "websocket":
        await _send_close(send, 1002)
        return

    try:
        user = await _authenticate_user(scope)
    except AuthenticationError:
        await _send_close(send, 4401)
        return
    except Exception:
        logger.exception("events_ws: unexpected error during authentication")
        await _send_close(send, 1011)
        return

    await send({"type": "websocket.accept"})

    stop_event = asyncio.Event()
    sender_task = asyncio.create_task(_stream_events(user.id, send, stop_event))
    receiver_task = asyncio.create_task(_receive_loop(receive, stop_event))

    try:
        done, pending = await asyncio.wait(
            [sender_task, receiver_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        # Propagate unexpected errors from the finished tasks (if any).
        for task in done:
            exc = task.exception()
            if exc:
                raise exc
    except Exception:
        logger.exception("events_ws: application error for user=%s", user.id)
        await _send_close(send, 1011)
    finally:
        if not sender_task.cancelled() and not sender_task.done():
            sender_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender_task
        if not receiver_task.cancelled() and not receiver_task.done():
            receiver_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await receiver_task
