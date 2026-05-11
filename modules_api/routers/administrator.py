# modules_api/administrator.py
from ninja import Router
from ninja.errors import HttpError
from typing import List
from ninja_jwt.authentication import JWTAuth

from core.models import BrandUser
from core.dependencies import get_current_tenant
from ..schemas import AdminUserListOut

router = Router(tags=["Administrator"], auth=JWTAuth())

@router.get("/{brand_id}/users", response=List[AdminUserListOut])
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