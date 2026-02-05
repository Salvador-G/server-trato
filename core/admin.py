from django.contrib import admin
from .models import (
    Brand,
    Role,
    Permission,
    RolePermission,
    BrandUser,
)
# Register your models here.
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "description")
    search_fields = ("code",)

@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "permission")
    list_filter = ("role",)

@admin.register(BrandUser)
class BrandUserAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "brand",
        "role",
        "is_active",
        "joined_at",
        "assigned_by",
    )
    list_filter = ("brand", "role", "is_active")
    search_fields = ("user__email", "brand__name")
    autocomplete_fields = ("user", "assigned_by")

