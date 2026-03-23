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