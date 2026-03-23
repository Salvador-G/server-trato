from django.contrib import admin
from .models import DocumentType, Document

@admin.register(DocumentType)
class DocumentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "brand")
    list_filter = ("brand",)

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("document_type", "customer", "brand", "created_at")
    list_filter = ("brand", "document_type")