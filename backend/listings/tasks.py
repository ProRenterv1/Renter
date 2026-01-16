"""Celery tasks for listings."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.settings_resolver import get_int

from .models import Listing

logger = logging.getLogger(__name__)


def _retention_days() -> int:
    default_days = getattr(settings, "LISTING_SOFT_DELETE_RETENTION_DAYS", 3)
    try:
        default_days = int(default_days)
    except (TypeError, ValueError):
        default_days = 3
    retention_days = get_int("LISTING_SOFT_DELETE_RETENTION_DAYS", default_days)
    if retention_days < 0:
        retention_days = 0
    return retention_days


@shared_task(name="listings.purge_soft_deleted_listings")
def purge_soft_deleted_listings() -> int:
    """
    Hard-delete listings that were soft-deleted at least the configured retention window.
    Returns the number of listings deleted.
    """
    now = timezone.now()
    cutoff = now - timedelta(days=_retention_days())

    qs = Listing.objects.filter(
        is_deleted=True,
        deleted_at__isnull=False,
        deleted_at__lte=cutoff,
    )

    count = qs.count()
    qs.delete()
    logger.info("listings: purged %s soft-deleted listings", count)
    return count
