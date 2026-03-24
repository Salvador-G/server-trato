from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# =========================
# BRAND (Tenant / Marca SaaS)
# =========================
class Brand(models.Model):
    name = models.CharField(max_length=150, verbose_name="Nombre Comercial")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"

    def __str__(self):
        return self.name
    
# =========================
# BRAND LEGAL PROFILE
# =========================
class BrandLegalProfile(models.Model):
    brand = models.OneToOneField(
        Brand, 
        on_delete=models.CASCADE, 
        related_name="legal_profile"
    )
    tax_id = models.CharField(
        max_length=50, 
        unique=True, # ¡Blindaje! Dos marcas no pueden usar el mismo RUC para pagar el SaaS
        verbose_name="RUC / ID Fiscal"
    )
    legal_name = models.CharField(max_length=255, verbose_name="Razón Social")
    fiscal_address = models.TextField(blank=True, null=True, verbose_name="Dirección Fiscal")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand Legal Profile"
        verbose_name_plural = "Brand Legal Profiles"

    def __str__(self):
        return f"{self.legal_name} ({self.tax_id})"

# =========================
# PERMISSION (Diccionario Global de Permisos)
# =========================
class Permission(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Ej: trade.contact, contract.generate"
    )
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return self.code

# =========================
# ROLE (Aislado por Marca)
# =========================
class Role(models.Model):
    # ¡CLAVE SAAS! El rol pertenece a una marca específica
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="roles") 
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # Crea la tabla pivot: role_permission automáticamente
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Una misma marca no puede tener dos roles que se llamen igual
        unique_together = ("brand", "name") 
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return f"{self.name} ({self.brand.name})"

# =========================
# BRAND_USER (Pivot: Trabajador ↔ Marca ↔ Rol)
# =========================
class BrandUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="brand_roles")
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="users")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_created"
    )

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "brand")
        verbose_name = "Brand User"
        verbose_name_plural = "Brand Users"

    def __str__(self):
        return f"{self.user} @ {self.brand} ({self.role.name})"