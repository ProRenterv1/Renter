from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_bookings_cache_for_users
from .models import Booking


@receiver(post_save, sender=Booking, dispatch_uid="bookings_cache_invalidate_on_save")
@receiver(post_delete, sender=Booking, dispatch_uid="bookings_cache_invalidate_on_delete")
def _invalidate_booking_cache(sender, instance: Booking, **kwargs):
    invalidate_bookings_cache_for_users([instance.owner_id, instance.renter_id])
