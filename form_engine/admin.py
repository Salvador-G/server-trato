from django.contrib import admin
from .models import FormularioEnvio, Formulario

# Register your models here.
@admin.register(Formulario)
class FormularioAdmin(admin.ModelAdmin):
    list_display = (
        "form_key",
        "brand",
        "version",
        "is_public",
        "is_active",
        "created_by",
        "created_at",
    )
    list_filter = ("brand", "is_public", "is_active")
    search_fields = ("form_key",)
    readonly_fields = ("created_at",)

@admin.register(FormularioEnvio)
class FormularioEnvioAdmin(admin.ModelAdmin):
    list_display = (
        "submission_id",
        "formulario",
        "source",
        "submitted_at",
    )
    list_filter = ("source", "submitted_at")
    readonly_fields = (
        "submission_id",
        "payload",
        "submitted_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False