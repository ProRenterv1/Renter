from __future__ import annotations

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.redis import read_user_events


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def events_stream(request):
    """
    Long-poll endpoint returning per-user events from Redis Streams.

    Query params:
    - cursor: last seen event id (Redis stream id).
      If omitted, default "$" (only new events).
    - timeout: blocking time in seconds (default 25, max 60).
    """
    user = request.user
    cursor = (request.query_params.get("cursor") or "").strip() or "$"
    try:
        timeout_sec = float(request.query_params.get("timeout", "25"))
    except ValueError:
        timeout_sec = 25.0
    timeout_sec = max(0.0, min(timeout_sec, 60.0))
    block_ms = int(timeout_sec * 1000)

    next_cursor, events = read_user_events(
        user_id=user.id,
        cursor=cursor,
        block_ms=block_ms,
        count=100,
    )

    return Response(
        {
            "cursor": next_cursor,
            "events": events,
            "now": timezone.now().isoformat(),
        },
        status=status.HTTP_200_OK,
    )
