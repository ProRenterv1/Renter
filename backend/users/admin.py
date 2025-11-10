from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "can_rent", "can_list", "is_staff", "is_active")
    fieldsets = BaseUserAdmin.fieldsets + (("Capabilities", {"fields": ("can_rent", "can_list")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Capabilities", {"fields": ("can_rent", "can_list")}),
    )
