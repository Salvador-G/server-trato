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