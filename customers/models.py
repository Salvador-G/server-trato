from django.db import models
from django.core.exceptions import ValidationError

# =========================
# COMPANY (B2B - Aislado por Marca)
# =========================
class Company(models.Model):
    brand = models.ForeignKey(
        "core.Brand", 
        on_delete=models.CASCADE, 
        related_name="companies"
    )
    tax_id = models.CharField(max_length=20, verbose_name="RUC / Identificación Fiscal")
    legal_name = models.CharField(max_length=255, verbose_name="Razón Social")
    fiscal_address = models.CharField(max_length=255, blank=True, verbose_name="Domicilio Fiscal")
    
    # Campo JSON para guardar datos dinámicos que vengan del form-builder
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Datos Extra")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        unique_together = ("brand", "tax_id") # Una marca no puede registrar dos veces el mismo RUC

    def __str__(self):
        return f"{self.legal_name} ({self.tax_id})"

# =========================
# CONTACT (El ser humano - Aislado por Marca)
# =========================
class Contact(models.Model):
    brand = models.ForeignKey(
        "core.Brand", 
        on_delete=models.CASCADE, 
        related_name="contacts"
    )
    full_name = models.CharField(max_length=255, verbose_name="Nombre Completo")
    email = models.EmailField(verbose_name="Correo Electrónico")
    phone = models.CharField(max_length=50, blank=True, verbose_name="Teléfono")
    
    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="contacts",
        verbose_name="Empresa"
    )
    
    is_primary_contact = models.BooleanField(
        default=False, 
        verbose_name="¿Es contacto principal?"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Contact"
        verbose_name_plural = "Contacts"

    def __str__(self):
        if self.company:
            return f"{self.full_name} @ {self.company.legal_name}"
        return self.full_name

# =========================
# CUSTOMER (El Nexo con tu Marca)
# =========================
class Customer(models.Model):
    CUSTOMER_TYPE_CHOICES = (
        ('B2B', 'Empresa (B2B)'),
        ('B2C', 'Individuo (B2C)'),
    )

    brand = models.ForeignKey(
        "core.Brand", 
        on_delete=models.CASCADE, 
        related_name="customers",
        verbose_name="Marca"
    )
    
    customer_type = models.CharField(
        max_length=3, 
        choices=CUSTOMER_TYPE_CHOICES,
        default='B2B',
        verbose_name="Tipo de Cliente"
    )

    company = models.ForeignKey(
        Company, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="customer_profiles",
        verbose_name="Empresa Asociada"
    )
    
    contact = models.ForeignKey(
        Contact, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name="customer_profiles",
        verbose_name="Contacto Asociado"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        unique_together = ("brand", "company") 

    def clean(self):
        super().clean()
        if self.customer_type == 'B2B' and not self.company:
            raise ValidationError("Un cliente B2B debe tener una Empresa (Company) asociada.")
        if self.customer_type == 'B2C' and not self.contact:
            raise ValidationError("Un cliente B2C debe tener un Contacto (Contact) asociado.")
        if self.customer_type == 'B2C' and self.company:
            raise ValidationError("Un cliente B2C no debería tener una Empresa asociada directamente.")

    def __str__(self):
        if self.customer_type == 'B2B' and self.company:
            return f"{self.company.legal_name} - {self.brand.name}"
        elif self.customer_type == 'B2C' and self.contact:
            return f"{self.contact.full_name} - {self.brand.name}"
        return f"Cliente {self.id} - {self.brand.name}"