from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import LoginEvent, PasswordResetChallenge, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "phone", "can_rent", "can_list", "is_staff", "is_active")
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Capabilities", {"fields": ("can_rent", "can_list")}),
        (
            "Address",
            {
                "fields": (
                    "street_address",
                    "city",
                    "province",
                    "postal_code",
                )
            },
        ),
        (
            "Security",
            {
                "fields": (
                    "phone",
                    "email_verified",
                    "phone_verified",
                    "last_login_ip",
                    "last_login_ua",
                    "login_alerts_enabled",
                )
            },
        ),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Capabilities", {"fields": ("can_rent", "can_list")}),
        (
            "Address",
            {
                "fields": (
                    "street_address",
                    "city",
                    "province",
                    "postal_code",
                )
            },
        ),
        (
            "Security",
            {
                "fields": (
                    "phone",
                    "email_verified",
                    "phone_verified",
                    "login_alerts_enabled",
                )
            },
        ),
    )
    readonly_fields = BaseUserAdmin.readonly_fields + ("last_login_ip", "last_login_ua")


@admin.register(LoginEvent)
class LoginEventAdmin(admin.ModelAdmin):
    list_display = ("user", "ip", "is_new_device", "created_at", "ua_hash")
    list_filter = ("is_new_device", "created_at")
    search_fields = ("user__username", "user__email", "ip", "ua_hash")
    readonly_fields = ("user", "ip", "user_agent", "ua_hash", "is_new_device", "created_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(PasswordResetChallenge)
class PasswordResetChallengeAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "channel",
        "contact",
        "attempts",
        "max_attempts",
        "expires_at",
        "consumed",
    )
    list_filter = ("channel", "consumed", "created_at")
    search_fields = ("user__username", "user__email", "contact")
    readonly_fields = ("code_hash", "created_at", "last_sent_at")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
