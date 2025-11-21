from django.contrib import admin

from .models import PromotedSlot


@admin.register(PromotedSlot)
class PromotedSlotAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "owner", "starts_at", "ends_at", "active")
    list_filter = ("active", "starts_at", "ends_at")
    search_fields = ("listing__title", "owner__username", "owner__email")
