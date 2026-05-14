# core/dependencies.py
from ninja.errors import HttpError
from .models import BrandUser

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