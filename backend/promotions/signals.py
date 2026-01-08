from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from listings.cache import invalidate_listing_feed_cache

from .cache import invalidate_active_promoted_listing_ids_cache
from .models import PromotedSlot


@receiver(post_save, sender=PromotedSlot, dispatch_uid="promotions_invalidate_on_save")
@receiver(post_delete, sender=PromotedSlot, dispatch_uid="promotions_invalidate_on_delete")
def _clear_promoted_listing_cache(sender, instance, **kwargs):
    invalidate_active_promoted_listing_ids_cache()
    invalidate_listing_feed_cache()
