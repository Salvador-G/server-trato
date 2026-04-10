# customers/admin.py
from django.contrib import admin
from .models import Company, Contact, Customer

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    # Ponemos la Razón Social y RUC primero, la Marca a la derecha
    list_display = ('legal_name', 'tax_id', 'brand', 'created_at')
    list_filter = ('brand', 'created_at')
    search_fields = ('legal_name', 'tax_id')
    ordering = ('-created_at',)

@admin.register(Contact)
class ContactAdmin(admin.ModelAdmin):
    # El humano primero, luego su empresa y finalmente la marca
    list_display = ('full_name', 'email', 'company', 'is_primary_contact', 'brand')
    list_filter = ('brand', 'is_primary_contact')
    search_fields = ('full_name', 'email', 'phone')
    # Permite buscar la empresa al asignar en lugar de un dropdown gigante
    autocomplete_fields = ('company',) 
    ordering = ('-created_at',)

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    # Usamos un método personalizado para la primera columna
    list_display = ('identidad_del_cliente', 'customer_type', 'brand', 'created_at')
    list_filter = ('brand', 'customer_type')
    # Permite buscar en los campos de las relaciones
    search_fields = (
        'company__legal_name', 
        'company__tax_id', 
        'contact__full_name', 
        'contact__email'
    )
    autocomplete_fields = ('brand', 'company', 'contact')
    ordering = ('-created_at',)

    def identidad_del_cliente(self, obj):
        """
        Unifica la vista para que el admin sepa exactamente quién es el cliente
        sin importar si es B2B o B2C, y oculta los campos vacíos.
        """
        if obj.customer_type == 'B2B' and obj.company:
            return f"🏢 {obj.company.legal_name} (RUC: {obj.company.tax_id})"
        elif obj.customer_type == 'B2C' and obj.contact:
            return f"👤 {obj.contact.full_name} ({obj.contact.email})"
        return f"⚠️ Cliente incompleto (ID: {obj.id})"
    
    # Nombre de la columna en el panel de Django
    identidad_del_cliente.short_description = "Identidad del Cliente"