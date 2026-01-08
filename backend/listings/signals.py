from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_categories_cache, invalidate_listing_feed_cache
from .models import Category, Listing, ListingPhoto


@receiver(post_save, sender=Listing, dispatch_uid="listing_feed_invalidate_on_save")
@receiver(post_delete, sender=Listing, dispatch_uid="listing_feed_invalidate_on_delete")
def _invalidate_listing_feed_on_listing_change(sender, instance, **kwargs):
    invalidate_listing_feed_cache()


@receiver(post_save, sender=ListingPhoto, dispatch_uid="listing_feed_invalidate_on_photo_save")
@receiver(post_delete, sender=ListingPhoto, dispatch_uid="listing_feed_invalidate_on_photo_delete")
def _invalidate_listing_feed_on_photo_change(sender, instance, **kwargs):
    invalidate_listing_feed_cache()


@receiver(post_save, sender=Category, dispatch_uid="categories_cache_invalidate_on_save")
@receiver(post_delete, sender=Category, dispatch_uid="categories_cache_invalidate_on_delete")
def _invalidate_categories_on_change(sender, instance, **kwargs):
    invalidate_categories_cache()
