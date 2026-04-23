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
    # La selección de la empresa matriz ahora es un campo del modelo (ForeignKey).
    # Usaremos el campo por defecto de ModelForm, así que no necesitamos redefinirlo aquí.

    # --- Campos del Dueño (Owner) ---
    owner_email = forms.EmailField(required=True, label="Email del Dueño")
    owner_password = forms.CharField(widget=forms.PasswordInput, required=True, label="Contraseña Temporal")
    owner_first_name = forms.CharField(max_length=150, required=True, label="Nombre del Dueño")
    owner_last_name = forms.CharField(max_length=150, required=True, label="Apellidos del Dueño")

    class Meta:
        model = Brand
        fields = ('name', 'legal_entity', 'is_active') # Incluimos legal_entity

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si la instancia ya existe (estamos EDITANDO una marca, no creándola)
        if self.instance and self.instance.pk:
            # Al editar, no necesitamos volver a pedir los datos del dueño
            self.fields['owner_email'].required = False
            self.fields['owner_password'].required = False
            self.fields['owner_first_name'].required = False
            self.fields['owner_last_name'].required = False
            
@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    form = BrandOnboardingForm
    list_display = ('name', 'get_tax_id', 'get_legal_name', 'is_active', 'created_at')
    search_fields = ('name', 'legal_entity__tax_id', 'legal_entity__legal_name')
    autocomplete_fields = ('legal_entity',) # <-- ¡SUPER ÚTIL! Permite buscar el RUC si hay muchos

    def get_tax_id(self, obj):
        """Muestra el RUC en la lista principal del admin"""
        if obj.legal_entity:
            return obj.legal_entity.tax_id
        return "Sin RUC"
    get_tax_id.short_description = "RUC / ID Fiscal"

    def get_legal_name(self, obj):
        """Muestra la razón social"""
        if obj.legal_entity:
            return obj.legal_entity.legal_name
        return "N/A"
    get_legal_name.short_description = "Razón Social"

    # Aquí definimos cómo se organiza visualmente el formulario en el panel
    fieldsets = (
        ('Datos Comerciales (Tenant)', {
            'fields': ('name', 'legal_entity', 'is_active'),
            'description': "La 'Legal Entity' es la empresa matriz (RUC). Puedes buscar una existente o crearla dándole al botón '+'.",
        }),
        ('Credenciales del Dueño (Solo Creación)', {
            'fields': ('owner_first_name', 'owner_last_name', 'owner_email', 'owner_password'),
            'description': "Estos datos solo se usarán al registrar una nueva marca para crear al usuario administrador principal."
        }),
    )

    def save_model(self, request, obj, form, change):
        """
        Sobrescribimos el guardado para orquestar la transacción atómica
        """
        # Verificamos si estamos CREANDO una marca nueva
        if not obj.pk:
            with transaction.atomic():
                # 1. Guardar la Marca Base (ahora incluye automáticamente el legal_entity seleccionado en el panel)
                super().save_model(request, obj, form, change)

                # 2. Crear el Rol 'Owner' aislado para esta marca específica
                owner_role, created = Role.objects.get_or_create(
                    brand=obj,
                    name="Owner",
                    defaults={"description": "Administrador principal y dueño de la cuenta SaaS."}
                )

                # 3. Crear el Usuario (o recuperarlo si ya existía en otra marca)
                email = form.cleaned_data['owner_email']
                user = User.objects.filter(email=email).first()
                if not user:
                    user = User.objects.create_user(
                        email=email,
                        password=form.cleaned_data['owner_password'],
                        first_name=form.cleaned_data['owner_first_name'],
                        last_name=form.cleaned_data['owner_last_name']
                    )

                # 4. Crear el BrandUser (Pivot: Trabajador ↔ Marca ↔ Rol)
                BrandUser.objects.create(
                    user=user,
                    brand=obj,
                    role=owner_role,
                    assigned_by=request.user # Registramos que el Superadmin hizo la asignación
                )
        
        # Si estamos EDITANDO una marca existente
        else:
            # Ya no necesitamos lógica compleja aquí, super() guarda el cambio de nombre o de legal_entity
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