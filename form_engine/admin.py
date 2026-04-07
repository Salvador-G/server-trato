from django.contrib import admin
from .models import Form, FormSubmission

@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = (
        "form_key",
        "brand",
        "version",
        "target_workflow",
        "is_public",
        "is_active",
        "created_by",
        "created_at",
    )
    list_filter = ("brand", "target_workflow", "is_public", "is_active")
    search_fields = ("form_key", "brand__name")
    readonly_fields = ("created_at", "updated_at")

@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "submission_id",
        "form",
        "customer",  # Agregado para ver qué cliente respondió
        "source",
        "submitted_at",
    )
    # Agregamos filtro por marca para facilitar la búsqueda en el admin
    list_filter = ("source", "submitted_at", "form__brand") 
    readonly_fields = (
        "submission_id",
        "payload",
        "submitted_at",
    )

    # Bloqueamos la creación/edición manual porque esto debe ser inmutable
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

