from django.contrib import admin
from .models import (
    Brand,
    Role,
    Permission,
    BrandUser,
)

@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    # Agregué 'brand' para que veas de qué empresa es el rol en el panel
    list_display = ("id", "name", "brand", "is_active") 
    list_filter = ("brand", "is_active")
    search_fields = ("name", "brand__name")

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "description")
    search_fields = ("code",)

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
    # Nota: Si autocomplete_fields da error, es porque necesitas configurar 
    # search_fields = ("email",) en el admin de tu app 'accounts'.
    autocomplete_fields = ("user", "assigned_by")