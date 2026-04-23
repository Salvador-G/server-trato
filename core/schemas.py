# core/schemas.py
from ninja import ModelSchema, Schema
from typing import List, Optional
from datetime import datetime
from .models import Brand, LegalEntity, Permission, Role, BrandUser # <-- IMPORTACIÓN ACTUALIZADA

# =========================
# SCHEMAS: LEGAL ENTITY (La Matriz / Empresa Legal)
# =========================
class LegalEntityOut(ModelSchema):
    class Meta:
        model = LegalEntity
        fields = ['id', 'tax_id', 'legal_name', 'fiscal_address']

class LegalEntityCreate(ModelSchema):
    class Meta:
        model = LegalEntity
        fields = ['tax_id', 'legal_name', 'fiscal_address']

class LegalEntityUpdate(ModelSchema):
    tax_id: Optional[str] = None
    legal_name: Optional[str] = None
    fiscal_address: Optional[str] = None
    
    class Meta:
        model = LegalEntity
        fields = ['tax_id', 'legal_name', 'fiscal_address']
        config = {"extra": "ignore"}
        
# =========================
# SCHEMAS: BRAND (Tenant)
# =========================
class BrandOut(ModelSchema):
    # Ya no es 'legal_profile', ahora es la entidad legal matriz
    legal_entity: Optional[LegalEntityOut] = None 
    
    class Meta:
        model = Brand
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']

class BrandCreate(ModelSchema):
    # Para crear una marca, opcionalmente podemos enviar el ID de la empresa matriz
    # si es que el usuario ya tiene una y quiere asociarle una nueva marca.
    legal_entity_id: Optional[int] = None 
    
    class Meta:
        model = Brand
        fields = ['name']

class BrandUpdate(ModelSchema):
    legal_entity_id: Optional[int] = None 
    
    class Meta:
        model = Brand
        fields = ['name', 'is_active']
        config = {"extra": "ignore"}

# =========================
# (El resto de Schemas de Role, Permission y BrandUser se mantienen iguales)
# =========================
class PermissionOut(ModelSchema):
    class Meta:
        model = Permission
        fields = ['id', 'code', 'description']

class RoleOut(ModelSchema):
    permissions: List[PermissionOut] 
    class Meta:
        model = Role
        fields = ['id', 'name', 'description', 'is_active', 'created_at']

class RoleCreate(ModelSchema):
    permission_ids: List[int] = [] 
    class Meta:
        model = Role
        fields = ['name', 'description']

class RoleUpdate(ModelSchema):
    permission_ids: Optional[List[int]] = None
    class Meta:
        model = Role
        fields = ['name', 'description', 'is_active']
        config = {"extra": "ignore"}

class UserNestedOut(Schema):
    id: int
    email: str

class UserMeOut(Schema):
    full_name: str
    role_name: str
    avatar_url: Optional[str] = None 
    
class BrandUserOut(ModelSchema):
    user: UserNestedOut 
    role: RoleOut       
    class Meta:
        model = BrandUser
        fields = ['id', 'is_active', 'joined_at']

class BrandUserCreate(Schema):
    user_id: int
    role_id: int

class BrandUserUpdate(Schema):
    role_id: Optional[int] = None
    is_active: Optional[bool] = None