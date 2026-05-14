# core/admin.py
from django import forms
from django.db import transaction
from django.contrib.auth import get_user_model
from django.contrib import admin
from .models import (
    Brand,
    LegalEntity, # <-- IMPORTACIÓN ACTUALIZADA
    Role,
    Permission,
    BrandUser,
    AuditLog
)

User = get_user_model()

# ==========================================
# 1. ENTIDADES LEGALES (Empresas Matriz)
# ==========================================
@admin.register(LegalEntity)
class LegalEntityAdmin(admin.ModelAdmin):
    list_display = ("id", "legal_name", "tax_id", "created_at")
    search_fields = ("legal_name", "tax_id")
    # Es buena práctica tener un buscador rápido por si tienes muchos RUCs registrados

# ==========================================
# 2. FORMULARIO DE ONBOARDING SAAS (Brands)
# ==========================================
class BrandOnboardingForm(forms.ModelForm):
    # En lugar de pedir textos sueltos, pedimos que seleccione al usuario que ya creó
    owner_user = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True),
        required=False,
        label="Seleccionar Dueño (Owner)",
        help_text="Selecciona el usuario que será el administrador principal de esta marca. Debes crearlo previamente en la sección 'Accounts'."
    )

    class Meta:
        model = Brand
        fields = ('name', 'legal_entity', 'is_active')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si la instancia ya existe (estamos EDITANDO la marca)
        if self.instance and self.instance.pk:
            # Ocultamos el campo porque el Owner solo se asigna al nacer la marca
            # Para cambiar o añadir dueños después, se usa la tabla BrandUser
            self.fields['owner_user'].widget = forms.HiddenInput()
            self.fields['owner_user'].required = False
        else:
            self.fields['owner_user'].required = True
            
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    form = BrandOnboardingForm
    list_display = ('name', 'get_tax_id', 'get_legal_name', 'is_active', 'created_at')
    search_fields = ('name', 'legal_entity__tax_id', 'legal_entity__legal_name')
    autocomplete_fields = ('legal_entity',) 

    def get_tax_id(self, obj):
        if obj.legal_entity:
            return obj.legal_entity.tax_id
        return "Sin RUC"
    get_tax_id.short_description = "RUC / ID Fiscal"

    def get_legal_name(self, obj):
        if obj.legal_entity:
            return obj.legal_entity.legal_name
        return "N/A"
    get_legal_name.short_description = "Razón Social"

    fieldsets = (
        ('Datos Comerciales (Tenant)', {
            'fields': ('name', 'legal_entity', 'is_active'),
            'description': "La 'Legal Entity' es la empresa matriz (RUC).",
        }),
        ('Asignación de Administrador (Solo Creación)', {
            'fields': ('owner_user',),
            'description': "Asigna a un usuario existente para que sea el Dueño (Owner) del Tenant. Si no existe, ve a la sección de Usuarios y créalo primero."
        }),
    )

    def save_model(self, request, obj, form, change):
        """
        Sobrescribimos el guardado para orquestar la transacción atómica
        """
        if not obj.pk:
            with transaction.atomic():
                # 1. Guardar la Marca Base
                super().save_model(request, obj, form, change)

                # 2. Crear el Rol 'Owner' aislado para esta marca
                owner_role, created = Role.objects.get_or_create(
                    brand=obj,
                    name="Owner",
                    defaults={"description": "Administrador principal y dueño de la cuenta SaaS."}
                )

                # 3. Vincular el usuario seleccionado con la marca recién creada
                selected_user = form.cleaned_data.get('owner_user')
                
                if selected_user:
                    BrandUser.objects.create(
                        user=selected_user,
                        brand=obj,
                        role=owner_role,
                        assigned_by=request.user # Tú, el superadmin
                    )
        else:
            # Si solo estamos editando el nombre de la marca o su estado
            super().save_model(request, obj, form, change)

# ==========================================
# 3. ROLES, PERMISOS Y USUARIOS
# ==========================================
@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
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
    autocomplete_fields = ("user", "assigned_by")
    
@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'actor', 'action', 'brand', 'ip_address')
    list_filter = ('action', 'brand', 'created_at')
    search_fields = ('actor__email', 'ip_address', 'user_agent')
    readonly_fields = ('brand', 'actor', 'action', 'details', 'ip_address', 'user_agent', 'created_at')
    
    # Ordenamiento por defecto en el admin
    ordering = ('-created_at',)

    # ==========================================
    # BLOQUEO DE MUTACIONES (Solo Lectura)
    # ==========================================
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False