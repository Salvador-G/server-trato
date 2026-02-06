from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# =========================
# BRAND
# =========================
class Brand(models.Model):
    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name


# =========================
# ROLE
# =========================
class Role(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


# =========================
# PERMISSION
# =========================
class Permission(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Ej: trade.contactar, contrato.generar"
    )
    description = models.TextField(blank=True)

    def __str__(self):
        return self.code


# =========================
# ROLE ↔ PERMISSION
# =========================
class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("role", "permission")

    def __str__(self):
        return f"{self.role} → {self.permission}"


# =========================
# BRAND ↔ USER (ROL POR MARCA)
# =========================
class BrandUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="brand_assignments_created"
    )

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "brand")

    def __str__(self):
        return f"{self.user} @ {self.brand} ({self.role})"
