"""Celery tasks for listings."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Listing

logger = logging.getLogger(__name__)


@shared_task(name="listings.purge_soft_deleted_listings")
def purge_soft_deleted_listings() -> int:
    """
    Hard-delete listings that were soft-deleted at least 7 days ago.
    Returns the number of listings deleted.
    """
    now = timezone.now()
    cutoff = now - timedelta(days=7)

    qs = Listing.objects.filter(
        is_deleted=True,
        deleted_at__isnull=False,
        deleted_at__lte=cutoff,
    )

    count = qs.count()
    qs.delete()
    logger.info("listings: purged %s soft-deleted listings", count)
    return count
