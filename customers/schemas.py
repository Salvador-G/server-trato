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