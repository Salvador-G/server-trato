# modules_api/administrator.py
import os
from ninja import Router, Header
from ninja.pagination import paginate, LimitOffsetPagination
from ninja.errors import HttpError
from typing import List
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404

from core.models import BrandUser, AuditLog
from core.dependencies import get_current_tenant, verify_module_access
from ..schemas import AdminUserListOut, UserDetailExtendedOut, AuditLogOut

router = Router(tags=["Administrator"], auth=JWTAuth())

@router.get("/{brand_id}/users", response=List[AdminUserListOut])
@paginate(LimitOffsetPagination)
def list_tenant_users(request, brand_id: int):
    # 1. Autenticación y Extracción del Perfil Tenant (Gatekeeper)
    # Verifica que el usuario pertenezca a la marca consultada
    current_tenant = get_current_tenant(request, brand_id)
    current_role_name = current_tenant.role.name.lower()

    # 2. Queryset Base optimizado con select_related
    # Solo traemos usuarios vinculados a ESTA marca, evitando N+1 queries al perfil
    qs = BrandUser.objects.filter(brand=current_tenant.brand).select_related(
        'user', 
        'role', 
        'user__profile'
    )

    # 3. Lógica de Jerarquía y Visibilidad (RBAC)
    if current_role_name == 'owner':
        # El Owner ve a todos
        pass 
    elif current_role_name == 'manager':
        # El Manager ve a todos EXCEPTO a los 'owner'
        qs = qs.exclude(role__name__iexact='owner')
    else:
        # Los roles operativos no tienen acceso a este panel
        raise HttpError(403, "No tienes permisos de administrador para ver esta lista.")

    # 4. Mapeo Manual al Esquema
    result = []
    for bu in qs:
        profile = getattr(bu.user, 'profile', None)
        
        # Armamos el nombre amigable
        full_name = f"{bu.user.first_name} {bu.user.last_name}".strip()
        if not full_name:
            full_name = bu.user.email.split('@')[0]

        result.append({
            "brand_user_id": bu.id,
            "user_id": bu.user.id,
            "full_name": full_name,
            "email": bu.user.email,
            "role_name": bu.role.name,
            "is_active": bu.is_active,
            "joined_at": bu.joined_at,
            "last_login": bu.user.last_login,
            "session_info": {
                "ip_address": profile.last_ip if profile else None,
                "browser_os": profile.last_user_agent if profile else None,
            }
        })

    return result

# ---------------------------------------------------------
# 1. DATOS PRINCIPALES DEL USUARIO (Para la cabecera/tarjeta)
# ---------------------------------------------------------
@router.get("/brand/employees/{user_id}", response=UserDetailExtendedOut)
def get_employee_details(request, user_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    # Validamos que el usuario realmente pertenezca a esta marca
    brand_user = get_object_or_404(BrandUser, user_id=user_id, brand=tenant.brand)
    user_obj = brand_user.user
    profile = getattr(user_obj, 'profile', None)

    return {
        "id": user_obj.id,
        "email": user_obj.email,
        "first_name": user_obj.first_name,
        "last_name": user_obj.last_name,
        "is_active": brand_user.is_active,
        "joined_at": brand_user.joined_at,
        "role_name": brand_user.role.name,
        "document_type": profile.document_type if profile else None,
        "document_id": profile.document_id if profile else None,
        "phone": profile.phone if profile else None,
        "address": profile.address if profile else None,
    }

# ---------------------------------------------------------
# 2. TIMELINE DE ACTIVIDAD (Excluye logins)
# ---------------------------------------------------------
@router.get("/brand/employees/{user_id}/activity", response=List[AuditLogOut])
@paginate(LimitOffsetPagination)
def get_employee_activity(request, user_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    # Validar que pertenece a la marca
    get_object_or_404(BrandUser, user_id=user_id, brand=tenant.brand)
    
    # Retornamos todas sus acciones en ESTA marca, excluyendo los inicios de sesión
    return AuditLog.objects.filter(
        brand=tenant.brand,
        actor_id=user_id
    ).exclude(
        action__in=['AUTH_LOGIN', 'AUTH_FAILED']
    ).order_by('-created_at')

# ---------------------------------------------------------
# 3. HISTORIAL DE SEGURIDAD Y SESIONES (Solo logins)
# ---------------------------------------------------------
@router.get("/brand/employees/{user_id}/sessions", response=List[AuditLogOut])
@paginate(LimitOffsetPagination)
def get_employee_sessions(request, user_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    # Validar que pertenece a la marca
    get_object_or_404(BrandUser, user_id=user_id, brand=tenant.brand)
    
    # Retornamos SOLO los eventos de autenticación
    # Nota: Si el login es global (antes de elegir marca), el 'brand' del AuditLog podría ser null. 
    # En ese caso podrías quitar el filtro de `brand=tenant.brand` solo para este endpoint, 
    # dependiendo de cómo guardes el AUTH_LOGIN.
    return AuditLog.objects.filter(
        actor_id=user_id,
        action__in=['AUTH_LOGIN', 'AUTH_FAILED']
    ).order_by('-created_at')