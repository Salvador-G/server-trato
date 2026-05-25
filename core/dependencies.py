# core/dependencies.py
from ninja.errors import HttpError
from .models import BrandUser
from typing import List

def get_current_tenant(request, brand_id: int) -> BrandUser:
    """
    Función helper SaaS: Verifica el acceso del usuario a la marca 
    y devuelve su perfil de inquilino.
    """
    user = request.user
    
    if not user.is_authenticated:
        raise HttpError(401, "Usuario no autenticado.")

    try:
        # Buscamos si el usuario pertenece a esta marca
        tenant_profile = BrandUser.objects.select_related('brand', 'role').get(
            user=user,
            brand_id=brand_id,
            is_active=True
        )
        
        if not tenant_profile.brand.is_active:
            raise HttpError(403, "Esta cuenta de empresa está inactiva.")
            
        return tenant_profile

    except BrandUser.DoesNotExist:
        raise HttpError(403, "No tienes acceso a este espacio de trabajo.")
    
def verify_module_access(tenant: BrandUser, required_role_code: str):
    """
    Bloquea el acceso si el usuario no tiene el rol necesario.
    'owner' y 'manager' siempre pasan.
    """
    role_name = tenant.role.name.lower()
    
    # Lista de roles con super-poderes dentro de la marca
    super_roles = ['owner', 'manager']
    
    # Si el rol actual no es super-poderoso y no es el rol específico requerido
    if role_name not in super_roles and role_name != required_role_code.lower():
        raise HttpError(
            403, 
            f"Permisos insuficientes. Se requiere rol de {required_role_code}, Manager u Owner."
        )
        
def get_authorized_brands(user, requested_brands: List[int], required_module: str = None) -> List[int]:
    """
    Función helper Dashboard: Filtra la lista de marcas pedidas y devuelve 
    SOLO los IDs a los que el usuario tiene acceso y permisos. (1 sola consulta SQL)
    """
    if not user.is_authenticated:
        raise HttpError(401, "Usuario no autenticado.")

    # 1. Buscamos todas las relaciones válidas de una sola vez
    tenants = BrandUser.objects.filter(
        user=user,
        brand_id__in=requested_brands,
        is_active=True,
        brand__is_active=True
    ).select_related('role')

    valid_brand_ids = []
    super_roles = ['owner', 'manager']

    # 2. Filtramos en memoria aplicando tu lógica de roles
    for tenant in tenants:
        role_name = tenant.role.name.lower()
        
        # Si no se requiere un módulo específico, o si tiene los super-poderes/rol adecuado
        if not required_module:
            valid_brand_ids.append(tenant.brand_id)
        elif role_name in super_roles or role_name == required_module.lower():
            valid_brand_ids.append(tenant.brand_id)

    # 3. Si después de filtrar no queda nada, bloqueamos el acceso
    if not valid_brand_ids:
        raise HttpError(403, "No tienes permisos para ver métricas en las marcas seleccionadas.")

    return valid_brand_ids