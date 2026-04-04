# core/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.db.models import ProtectedError
from django.db import transaction
from ninja_jwt.authentication import JWTAuth
from django.contrib.auth import get_user_model

from .models import Role, Brand, BrandUser
from .schemas import (
    RoleOut, RoleCreate, RoleUpdate,
    BrandOut, BrandCreate, BrandUpdate,
    BrandUserOut, BrandUserCreate, BrandUserUpdate, UserMeOut
)
from .dependencies import get_current_tenant

# Obtenemos el modelo de usuario de forma segura
User = get_user_model()

# Protegemos todo el router con JWT
router = Router(tags=["Core - SaaS"], auth=JWTAuth())

# ==========================================
# ENDPOINTS DE MIS MARCAS (DESCUBRIMIENTO Y CREACIÓN)
# ==========================================

@router.get("/my-brands", response=List[BrandOut])
def list_my_brands(request):
    """Lista las marcas a las que pertenece el usuario autenticado."""
    return Brand.objects.filter(users__user=request.user, users__is_active=True)

@router.post("/my-brands", response={201: BrandOut})
def create_my_brand(request, payload: BrandCreate):
    """Crea una nueva marca y asigna al usuario como dueño."""
    with transaction.atomic():
        new_brand = Brand.objects.create(name=payload.name)
        owner_role = Role.objects.create(
            brand=new_brand,
            name="Owner",
            description="Dueño de la cuenta con acceso total."
        )
        BrandUser.objects.create(
            user=request.user,
            brand=new_brand,
            role=owner_role,
            assigned_by=request.user
        )
    return 201, new_brand


# ==========================================
# ENDPOINTS DE LA MARCA (TENANT ACTUAL)
# ==========================================

@router.get("/brand", response=BrandOut)
def get_current_brand(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Obtiene detalles de la marca actual (usando el Header X-Brand-Id)"""
    tenant = get_current_tenant(request, x_brand_id)
    return tenant.brand

@router.patch("/brand", response=BrandOut)
def update_current_brand(request, payload: BrandUpdate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Actualiza la marca actual"""
    tenant = get_current_tenant(request, x_brand_id)
    brand = tenant.brand
    update_data = payload.dict(exclude_unset=True)
    
    if update_data:
        for attr, value in update_data.items():
            setattr(brand, attr, value)
        brand.save(update_fields=update_data.keys())
    return brand

@router.get("/me", response=UserMeOut)
def get_me_context(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    user = tenant.user

    first = getattr(user, 'first_name', '')
    last = getattr(user, 'last_name', '')
    full_name = f"{first} {last}".strip()
    
    if not full_name:
        full_name = user.email.split('@')[0].capitalize()

    # NUEVO: Lógica segura para extraer la URL del Avatar
    avatar_url = None
    # 1. Verificamos que el usuario tenga un perfil (hasattr)
    # 2. Verificamos que el campo avatar tenga un archivo asociado
    if hasattr(user, 'profile') and user.profile.avatar:
        # build_absolute_uri convierte "/media/avatars/foto.jpg" en "http://127.0.0.1:8000/media/avatars/foto.jpg"
        avatar_url = request.build_absolute_uri(user.profile.avatar.url)

    return {
        "full_name": full_name,
        "role_name": tenant.role.name,
        "avatar_url": avatar_url
    }
    
# ==========================================
# ENDPOINTS DE ROLES (AISLADOS POR MARCA)
# ==========================================

@router.get("/roles", response=List[RoleOut])
def list_roles(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Lista roles de la marca actual"""
    tenant = get_current_tenant(request, x_brand_id)
    return Role.objects.filter(brand=tenant.brand)

@router.post("/roles", response={201: RoleOut})
def create_role(request, payload: RoleCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Crea un rol en la marca actual"""
    tenant = get_current_tenant(request, x_brand_id)
    data = payload.dict(exclude={'permission_ids'})
    role = Role.objects.create(brand=tenant.brand, **data)
    
    if payload.permission_ids:
        role.permissions.set(payload.permission_ids)
    return 201, role

@router.get("/roles/{role_id}", response=RoleOut)
def get_role(request, role_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Obtiene un rol por ID (filtrado por marca)"""
    tenant = get_current_tenant(request, x_brand_id)
    return get_object_or_404(Role, id=role_id, brand=tenant.brand)

@router.patch("/roles/{role_id}", response=RoleOut)
def update_role(request, role_id: int, payload: RoleUpdate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Actualiza un rol por ID"""
    tenant = get_current_tenant(request, x_brand_id)
    role = get_object_or_404(Role, id=role_id, brand=tenant.brand)
    update_data = payload.dict(exclude_unset=True, exclude={'permission_ids'})
    
    if update_data:
        for attr, value in update_data.items():
            setattr(role, attr, value)
        role.save(update_fields=update_data.keys())
        
    if payload.permission_ids is not None:
        role.permissions.set(payload.permission_ids)
    return role

@router.delete("/roles/{role_id}", response={204: None})
def delete_role(request, role_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Elimina un rol"""
    tenant = get_current_tenant(request, x_brand_id)
    role = get_object_or_404(Role, id=role_id, brand=tenant.brand)
    
    try:
        role.delete()
        return 204, None
    except ProtectedError:
        raise HttpError(400, "No puedes eliminar este rol porque hay usuarios asignados a él.")


# ==========================================
# ENDPOINTS DE EQUIPO (MIEMBROS DE LA MARCA)
# ==========================================

@router.get("/members", response=List[BrandUserOut])
def list_members(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Lista los miembros de la marca actual"""
    tenant = get_current_tenant(request, x_brand_id)
    return BrandUser.objects.filter(brand=tenant.brand).select_related('user', 'role')

@router.post("/members", response={201: BrandUserOut})
def add_member(request, payload: BrandUserCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Invita a un usuario a la marca actual"""
    tenant = get_current_tenant(request, x_brand_id)
    user_to_add = get_object_or_404(User, id=payload.user_id)
    role_to_assign = get_object_or_404(Role, id=payload.role_id, brand=tenant.brand)
    
    if BrandUser.objects.filter(user=user_to_add, brand=tenant.brand).exists():
        raise HttpError(400, "Este usuario ya es miembro de esta empresa.")
        
    new_member = BrandUser.objects.create(
        user=user_to_add,
        brand=tenant.brand,
        role=role_to_assign,
        assigned_by=request.user
    )
    return 201, new_member

@router.patch("/members/{member_id}", response=BrandUserOut)
def update_member(request, member_id: int, payload: BrandUserUpdate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Cambia el rol o estado de un miembro"""
    tenant = get_current_tenant(request, x_brand_id)
    member = get_object_or_404(BrandUser, id=member_id, brand=tenant.brand)
    
    if payload.role_id is not None:
        new_role = get_object_or_404(Role, id=payload.role_id, brand=tenant.brand)
        member.role = new_role
        
    if payload.is_active is not None:
        if payload.is_active is False and member.user == request.user:
            raise HttpError(400, "No puedes desactivarte a ti mismo.")
        member.is_active = payload.is_active
        
    member.save()
    return member

@router.delete("/members/{member_id}", response={204: None})
def remove_member(request, member_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Elimina a un miembro del espacio de trabajo"""
    tenant = get_current_tenant(request, x_brand_id)
    member = get_object_or_404(BrandUser, id=member_id, brand=tenant.brand)
    
    if member.user == request.user:
        raise HttpError(400, "No puedes eliminarte a ti mismo. Usa la opción de salir.")
        
    member.delete()
    return 204, None