from __future__ import annotations

import logging
import time

from celery import shared_task

from core.redis import get_redis_client

logger = logging.getLogger(__name__)

CELERY_HEARTBEAT_KEY = "ops:celery:last_seen"
CELERY_HEARTBEAT_TTL_SECONDS = 300


@shared_task(name="operator_health_ping")
def operator_health_ping() -> float | None:
    """
    Periodic heartbeat used by /api/operator/health/ to detect if Celery is running.

    Writes current epoch seconds into Redis with a TTL.
    """

    now = time.time()
    try:
        client = get_redis_client()
        client.setex(CELERY_HEARTBEAT_KEY, CELERY_HEARTBEAT_TTL_SECONDS, str(now))
        return float(now)
    except Exception:
        logger.warning("operator_health_ping: failed to write heartbeat", exc_info=True)
        return None
