from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, List, Tuple

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_redis_client() -> "redis.Redis":
    """
    Return a Redis client configured from settings.REDIS_URL.
    Safe to call from views and Celery tasks.
    """
    url = getattr(settings, "REDIS_URL", None)
    if not url:
        raise RuntimeError("REDIS_URL is not configured")
    return redis.Redis.from_url(url)


def _user_stream_key(user_id: int) -> str:
    return f"events:user:{int(user_id)}"


def push_event(user_id: int, event_type: str, payload: Dict[str, Any]) -> str | None:
    """
    Append an event for a single user into a Redis Stream.

    - user_id: Django User.id
    - event_type: e.g. "chat:new_message", "booking:status_changed"
    - payload: JSON-serializable dict; stored as a single 'payload' field.

    Returns the stream entry ID on success, or None on error.
    """
    stream_key = _user_stream_key(user_id)
    try:
        data = {
            "type": event_type,
            "payload": json.dumps(payload or {}, separators=(",", ":")),
        }
        client = get_redis_client()
        entry_id = client.xadd(stream_key, data, maxlen=1000, approximate=True)
        if isinstance(entry_id, bytes):
            entry_id = entry_id.decode("utf-8")
        return str(entry_id)
    except Exception:
        logger.warning(
            "events: failed to push event for user %s type=%s",
            user_id,
            event_type,
            exc_info=True,
        )
        return None


def read_user_events(
    user_id: int,
    *,
    cursor: str,
    block_ms: int,
    count: int = 100,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Blocking read from the user's event stream using XREAD.

    - cursor: last seen ID. "0-0" for from-start, "$" for only new events.
    - block_ms: how long to block in milliseconds.
    - count: max events.

    Returns (next_cursor, events), where events are:
    { "id": str, "type": str, "payload": dict }
    """
    stream_key = _user_stream_key(user_id)
    client = get_redis_client()
    try:
        records = client.xread(
            {stream_key: cursor},
            count=count,
            block=max(block_ms, 0),
        )
    except Exception:
        logger.warning(
            "events: XREAD failed for user %s stream %s cursor %s",
            user_id,
            stream_key,
            cursor,
            exc_info=True,
        )
        return cursor, []

    if not records:
        return cursor, []

    _, entries = records[0]
    events: List[Dict[str, Any]] = []
    last_id = cursor

    for raw_id, fields in entries:
        if isinstance(raw_id, bytes):
            raw_id = raw_id.decode("utf-8")
        last_id = str(raw_id)

        field_dict: Dict[str, Any] = {}
        for k, v in fields.items():
            key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
            if isinstance(v, bytes):
                v = v.decode("utf-8")
            field_dict[key] = v

        event_type = field_dict.get("type") or ""
        payload_raw = field_dict.get("payload") or "{}"
        try:
            payload = json.loads(payload_raw)
        except Exception:
            payload = {"raw": payload_raw}

        events.append(
            {
                "id": last_id,
                "type": event_type,
                "payload": payload,
            }
        )

    return last_id, events
