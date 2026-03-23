from django.contrib import admin
from .models import Company, Contact, Customer

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ("legal_name", "tax_id", "brand", "created_at")
    list_filter = ("brand",)
    search_fields = ("legal_name", "tax_id")

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "company", "brand", "is_primary_contact")
    list_filter = ("brand", "is_primary_contact")
    search_fields = ("full_name", "email")

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "brand", "customer_type", "company", "contact")
    list_filter = ("brand", "customer_type")