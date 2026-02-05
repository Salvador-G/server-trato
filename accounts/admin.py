from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    list_display = ("email", "is_staff", "is_active", "created_at")
    list_filter = ("is_staff", "is_active")

    ordering = ("email",)
    search_fields = ("email",)

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permisos", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Estado", {"fields": ("is_active",)}),
        ("Fechas", {"fields": ("last_login", "created_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2", "is_staff", "is_superuser"),
            },
        ),
    )
