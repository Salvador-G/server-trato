# core/schemas.py
from ninja import ModelSchema, Schema
from typing import List, Optional
from datetime import datetime
from .models import Brand, Permission, Role, BrandUser

# =========================
# SCHEMAS: BRAND
# =========================
class BrandOut(ModelSchema):
    class Meta:
        model = Brand
        fields = ['id', 'name', 'is_active', 'created_at', 'updated_at']

class BrandCreate(ModelSchema):
    class Meta:
        model = Brand
        fields = ['name']

class BrandUpdate(ModelSchema):
    class Meta:
        model = Brand
        fields = ['name', 'is_active']
        config = {"extra": "ignore"}

# =========================
# SCHEMAS: PERMISSION
# =========================
class PermissionOut(ModelSchema):
    class Meta:
        model = Permission
        fields = ['id', 'code', 'description']

# =========================
# SCHEMAS: ROLE
# =========================
class RoleOut(ModelSchema):
    # MAGIA NINJA: Anidamos los permisos para que el frontend 
    # reciba todo en una sola petición.
    permissions: List[PermissionOut] 
    
    class Meta:
        model = Role
        fields = ['id', 'name', 'description', 'is_active', 'created_at']

class RoleCreate(ModelSchema):
    # Pedimos una lista de IDs de permisos de forma opcional
    permission_ids: List[int] = [] 
    
    class Meta:
        model = Role
        fields = ['name', 'description'] # Omitimos brand_id por seguridad SaaS

class RoleUpdate(ModelSchema):
    permission_ids: Optional[List[int]] = None
    
    class Meta:
        model = Role
        fields = ['name', 'description', 'is_active']
        config = {"extra": "ignore"}

# =========================
# SCHEMAS: BRAND_USER (Trabajadores)
# =========================
# Creamos un mini-schema de usuario para no importar desde accounts 
# y evitar un error de "importación circular"
class UserNestedOut(Schema):
    id: int
    email: str

class BrandUserOut(ModelSchema):
    user: UserNestedOut # Devolvemos el email del usuario
    role: RoleOut       # Devolvemos el detalle del rol (y sus permisos)
    
    class Meta:
        model = BrandUser
        fields = ['id', 'is_active', 'joined_at']

class BrandUserCreate(Schema):
    # Usamos Schema normal porque recibiremos IDs, no objetos enteros
    user_id: int
    role_id: int

class BrandUserUpdate(Schema):
    role_id: Optional[int] = None
    is_active: Optional[bool] = None