from django.contrib import admin

from .models import DbSetting, FeatureFlag, MaintenanceBanner, OperatorJobRun


class UpdatedByAdminMixin:
    def save_model(self, request, obj, form, change):
        if getattr(request, "user", None) and request.user.is_authenticated:
            obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DbSetting)
class DbSettingAdmin(UpdatedByAdminMixin, admin.ModelAdmin):
    list_display = ("key", "value_type", "effective_at", "updated_at", "updated_by")
    search_fields = ("key", "description")
    list_filter = ("value_type",)
    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)


@admin.register(FeatureFlag)
class FeatureFlagAdmin(UpdatedByAdminMixin, admin.ModelAdmin):
    list_display = ("key", "enabled", "updated_at", "updated_by")
    search_fields = ("key",)
    list_filter = ("enabled",)
    date_hierarchy = "updated_at"
    ordering = ("key",)


@admin.register(MaintenanceBanner)
class MaintenanceBannerAdmin(UpdatedByAdminMixin, admin.ModelAdmin):
    list_display = ("enabled", "severity", "updated_at", "updated_by")
    search_fields = ("message",)
    list_filter = ("enabled", "severity")
    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)


@admin.register(OperatorJobRun)
class OperatorJobRunAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "created_at", "finished_at", "requested_by")
    search_fields = ("name",)
    list_filter = ("status", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

    def save_model(self, request, obj, form, change):
        if (
            not change
            and getattr(request, "user", None)
            and request.user.is_authenticated
            and obj.requested_by_id is None
        ):
            obj.requested_by = request.user
        super().save_model(request, obj, form, change)
