```python
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


# customers/schemas.py
from ninja import ModelSchema, Schema
from typing import Optional, Any, Dict
from .models import Company, Contact, Customer

# =========================
# SCHEMAS: COMPANY (B2B)
# =========================
class CompanyOut(ModelSchema):
    class Meta:
        model = Company
        fields = ['id', 'tax_id', 'legal_name', 'fiscal_address', 'metadata', 'created_at', 'updated_at']

class CompanyCreate(ModelSchema):
    # Definimos metadata como un diccionario explícito (JSON)
    metadata: Dict[str, Any] = {}
    
    class Meta:
        model = Company
        fields = ['tax_id', 'legal_name', 'fiscal_address']

class CompanyUpdate(ModelSchema):
    metadata: Optional[Dict[str, Any]] = None
    
    class Meta:
        model = Company
        fields = ['tax_id', 'legal_name', 'fiscal_address']
        config = {"extra": "ignore"}

# =========================
# SCHEMAS: CONTACT (Personas)
# =========================
class ContactOut(ModelSchema):
    company: Optional[CompanyOut] = None # Anidamos la empresa si el contacto pertenece a una
    
    class Meta:
        model = Contact
        fields = ['id', 'full_name', 'email', 'phone', 'is_primary_contact', 'created_at']

class ContactCreate(ModelSchema):
    company_id: Optional[int] = None
    
    class Meta:
        model = Contact
        fields = ['full_name', 'email', 'phone', 'is_primary_contact']

class ContactUpdate(ModelSchema):
    company_id: Optional[int] = None
    
    class Meta:
        model = Contact
        fields = ['full_name', 'email', 'phone', 'is_primary_contact']
        config = {"extra": "ignore"}

# =========================
# SCHEMAS: CUSTOMER (El Nexo)
# =========================
class CustomerOut(ModelSchema):
    # Anidamos las relaciones para que el frontend tenga todo de un solo golpe
    company: Optional[CompanyOut] = None
    contact: Optional[ContactOut] = None
    
    class Meta:
        model = Customer
        fields = ['id', 'customer_type', 'created_at', 'updated_at']

class CustomerCreate(Schema):
    # Usamos Schema normal en vez de ModelSchema porque tenemos validaciones personalizadas
    customer_type: str # 'B2B' o 'B2C'
    company_id: Optional[int] = None
    contact_id: Optional[int] = None

class CustomerUpdate(Schema):
    customer_type: Optional[str] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None


# customers/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from ninja_jwt.authentication import JWTAuth

# Importamos los modelos y schemas locales
from .models import Company, Contact, Customer
from .schemas import (
    CompanyOut, CompanyCreate, CompanyUpdate,
    ContactOut, ContactCreate, ContactUpdate,
    CustomerOut, CustomerCreate, CustomerUpdate
)

# ¡MAGIA DRY! Importamos la dependencia de seguridad desde la app core
from core.dependencies import get_current_tenant

router = Router(tags=["Customers (B2B/B2C)"], auth=JWTAuth())

# ==========================================
# ENDPOINTS: COMPANY (B2B)
# ==========================================

@router.get("/companies", response=List[CompanyOut])
def list_companies(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Lista todas las empresas (B2B) de la marca actual"""
    tenant = get_current_tenant(request, x_brand_id)
    return Company.objects.filter(brand=tenant.brand)

@router.post("/companies", response={201: CompanyOut})
def create_company(request, payload: CompanyCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Crea una nueva empresa B2B"""
    tenant = get_current_tenant(request, x_brand_id)
    company = Company.objects.create(brand=tenant.brand, **payload.dict())
    return 201, company

@router.get("/companies/{company_id}", response=CompanyOut)
def get_company(request, company_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    return get_object_or_404(Company, id=company_id, brand=tenant.brand)

@router.patch("/companies/{company_id}", response=CompanyOut)
def update_company(request, company_id: int, payload: CompanyUpdate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    company = get_object_or_404(Company, id=company_id, brand=tenant.brand)
    
    update_data = payload.dict(exclude_unset=True)
    for attr, value in update_data.items():
        setattr(company, attr, value)
    
    if update_data:
        company.save()
    return company

# ==========================================
# ENDPOINTS: CONTACTS (Personas físicas)
# ==========================================

@router.get("/contacts", response=List[ContactOut])
def list_contacts(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    return Contact.objects.filter(brand=tenant.brand).select_related('company')

@router.post("/contacts", response={201: ContactOut})
def create_contact(request, payload: ContactCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    data = payload.dict(exclude={'company_id'})
    
    # Si envían un company_id, validamos que la empresa sea de esta marca
    company = None
    if payload.company_id:
        company = get_object_or_404(Company, id=payload.company_id, brand=tenant.brand)
        
    contact = Contact.objects.create(brand=tenant.brand, company=company, **data)
    return 201, contact

@router.patch("/contacts/{contact_id}", response=ContactOut)
def update_contact(request, contact_id: int, payload: ContactUpdate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    contact = get_object_or_404(Contact, id=contact_id, brand=tenant.brand)
    
    update_data = payload.dict(exclude_unset=True, exclude={'company_id'})
    
    if 'company_id' in payload.dict(exclude_unset=True):
        if payload.company_id is None:
            contact.company = None
        else:
            contact.company = get_object_or_404(Company, id=payload.company_id, brand=tenant.brand)

    for attr, value in update_data.items():
        setattr(contact, attr, value)
        
    contact.save()
    return contact

# ==========================================
# ENDPOINTS: CUSTOMER (El Anclaje Comercial)
# ==========================================

@router.get("/customers", response=List[CustomerOut])
def list_customers(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    return Customer.objects.filter(brand=tenant.brand).select_related('company', 'contact')

@router.post("/customers", response={201: CustomerOut})
def create_customer(request, payload: CustomerCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    customer = Customer(brand=tenant.brand, customer_type=payload.customer_type)
    
    # Validamos relaciones de forma segura (Aislamiento de marca)
    if payload.company_id:
        customer.company = get_object_or_404(Company, id=payload.company_id, brand=tenant.brand)
    if payload.contact_id:
        customer.contact = get_object_or_404(Contact, id=payload.contact_id, brand=tenant.brand)
        
    try:
        # Ejecutamos las validaciones estrictas que creaste en tu models.py
        customer.clean() 
        customer.save()
        return 201, customer
    except ValidationError as e:
        # Si falla tu clean() (ej: B2B sin empresa), devolvemos error 400 limpio al frontend
        error_msg = e.messages[0] if hasattr(e, 'messages') else str(e)
        raise HttpError(400, error_msg)

@router.delete("/customers/{customer_id}", response={204: None})
def delete_customer(request, customer_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    customer = get_object_or_404(Customer, id=customer_id, brand=tenant.brand)
    customer.delete()
    return 204, None
```