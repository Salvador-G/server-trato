# accounts/routers.py
from ninja import Router, Schema, File, Header
from ninja.files import UploadedFile
from django.db import transaction
from django.db.models import Q
from django.contrib.auth.models import update_last_login
from ninja.errors import HttpError
from typing import List
from django.contrib.auth import get_user_model, authenticate
from django.shortcuts import get_object_or_404
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.tokens import RefreshToken
from core.dependencies import get_current_tenant
from core.utils.audit import log_audit_event
from core.utils.network import get_client_ip, rate_limit

from core.models import Brand, BrandUser, Role
from .schemas import (AdminUserUpdate, UserOut, UserCreate, UserUpdate,
                      EmployeeCreateInput, UserMeUpdate, ChangePasswordInput)
from .models import UserProfile

User = get_user_model()

# ==========================================
# 1. ESQUEMA DE LOGIN LIMPIO
# ==========================================
class LoginInput(Schema):
    email: str
    password: str
    brand_id: int = None  # <-- Opcional, pero útil si quieres validar que el usuario pertenece a la marca desde el login
    
# ==========================================
# ROUTER DE AUTENTICACIÓN (PÚBLICO)
# ==========================================
auth_router = Router(tags=["Auth"])

@auth_router.post("/pair")
@rate_limit(max_requests=5, window_seconds=60) # Protección contra fuerza bruta: 5 intentos por minuto por IP
def custom_login(request, payload: LoginInput):
    """
    Endpoint de Login.
    Protegido contra fuerza bruta: Máximo 5 intentos por minuto por IP.
    """
    user = authenticate(request, email=payload.email, password=payload.password)
    
    if not user:
        # Auditoría simple
        log_audit_event(
            request=request,
            action='AUTH_FAILED',
            details={"email_attempt": payload.email}
        )
        raise HttpError(401, "Usuario o contraseña incorrectos")

    if not user.is_active:
        raise HttpError(403, "Esta cuenta está inactiva.")

    # Actualizar IP y Dispositivo
    ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
    
    # 2. Reemplazamos el 'if hasattr' por 'get_or_create'
    # Esto garantiza que el perfil exista sí o sí.
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # 3. Asignamos los valores y guardamos
    profile.last_ip = ip
    profile.last_user_agent = user_agent
    profile.save(update_fields=['last_ip', 'last_user_agent'])

    update_last_login(None, user)
    
    # Auditoría de Login Global (Sin vincular a Tenant)
    log_audit_event(
        request=request,
        action='AUTH_LOGIN',
        actor=user,
        details={"login_method": "credentials"}
    )

    refresh = RefreshToken.for_user(user)
    
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


# ==========================================
# ROUTER DE CUENTAS (PROTEGIDO)
# ==========================================
router = Router(tags=["Accounts"], auth=JWTAuth())

@router.post("/users", response={201: UserOut})
def create_user(request, payload: UserCreate):
    """Crea un nuevo usuario usando el UserManager personalizado"""
    
    # UserManager se encarga de validar el email y encriptar el password
    user = User.objects.create_user(
        email=payload.email,
        password=payload.password
    )
    
    return 201, user

# Endpoint para iniciar sesion (Obtener datos propios)
@router.get("/users/me", response=UserOut)
def get_me(request):
    """Devuelve los datos del usuario autenticado actualmente"""
    # Gracias a auth=JWTAuth() en el router, request.user ya es el usuario real
    return request.user

@router.patch("/users/me/update", response=UserOut)
def update_me(request, payload: UserMeUpdate):
    """Actualiza la información básica y el perfil del usuario autenticado"""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)

    # 1. Actualizamos datos del User (Nombres)
    if payload.first_name is not None:
        user.first_name = payload.first_name
    if payload.last_name is not None:
        user.last_name = payload.last_name
    user.save(update_fields=['first_name', 'last_name'])

    # 2. Actualizamos datos del Perfil (Contacto y Legales)
    if payload.phone is not None:
        profile.phone = payload.phone
    if payload.document_type is not None:
        profile.document_type = payload.document_type
    if payload.document_id is not None:
        profile.document_id = payload.document_id
    if payload.address is not None:
        profile.address = payload.address
    profile.save()

    log_audit_event(
        request=request,
        action='PROFILE_UPDATED',
        actor=user,
        details={
            "message": "El usuario actualizó sus datos personales de contacto.",
            # Opcional: podrías guardar los campos que cambiaron
        }
    )
    
    return user

@router.post("/users/me/change-password")
def change_password(request, payload: ChangePasswordInput):
    """Cambia la contraseña validando la contraseña anterior"""
    user = request.user
    
    # 1. Validar que la contraseña actual ingresada sea correcta
    if not user.check_password(payload.current_password):
        raise HttpError(400, "La contraseña actual es incorrecta.")
    
    # 2. Asignar la nueva contraseña de forma encriptada
    user.set_password(payload.new_password)
    user.save(update_fields=['password'])
    
    ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')[:255]
    
    # Opcional: Registrar en auditoría
    log_audit_event(
        request=request,
        action='ROLE_CHANGED', # O crea un 'PASSWORD_CHANGED' en tu log
        actor=user,
        details={
            "message": "Cambio de contraseña exitoso",
            "ip_address": ip, # Dejamos constancia de la IP exacta
            "user_agent": user_agent # Dejamos constancia si usó Chrome, Safari, móvil, etc.
        }
    )
    
    return {"success": True, "message": "Contraseña actualizada exitosamente."}

@router.post("/users/me/avatar")
def upload_avatar(request, file: UploadedFile = File(...)):
    """Sube y actualiza la foto de perfil del usuario"""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    
    # Validaciones básicas de seguridad para imágenes
    if not file.content_type.startswith("image/"):
        raise HttpError(400, "El archivo debe ser una imagen válida.")
    
    if file.size > 5 * 1024 * 1024: # Límite de 5MB
        raise HttpError(400, "La imagen no debe pesar más de 5MB.")

    # Guardar el archivo en el ImageField
    profile.avatar.save(file.name, file)
    
    # Retornamos la URL relativa para que el frontend la muestre
    return {"success": True, "avatar_url": profile.avatar.url}

@router.get("/users", response=List[UserOut])
def list_users(request):
    """Lista de usuarios globales (SOLO PARA SUPERADMINS)"""
    if not request.user.is_superuser:
        raise HttpError(403, "Acceso denegado. Solo superadministradores pueden ver el directorio global.")
    return User.objects.all()

@router.get("/users/{user_id}", response=UserOut)
def get_user(request, user_id: int):
    """Obtiene un usuario por su ID"""
    user = get_object_or_404(User, id=user_id)
    return user

@router.patch("/users/{user_id}", response=UserOut)
def partial_update_user(request, user_id: int, payload: UserUpdate):
    """Actualización de perfil propio"""
    # Regla: Solo puedes actualizarte a TI MISMO por este endpoint
    if request.user.id != user_id:
        raise HttpError(403, "No tienes permiso para editar el perfil de otro usuario.")
    
    user = get_object_or_404(User, id=user_id)
    update_data = payload.dict(exclude_unset=True)
    
    for attr, value in update_data.items():
        setattr(user, attr, value)
    user.save(update_fields=update_data.keys())
    
    return user

@router.patch("/admin/users/{user_id}/permissions", response=UserOut)
def update_user_permissions(request, user_id: int, payload: AdminUserUpdate):
    """Endpoint dedicado a privilegios (SOLO PARA SUPERADMINS)"""
    if not request.user.is_superuser:
        raise HttpError(403, "Solo un superadministrador puede alterar privilegios.")
        
    user = get_object_or_404(User, id=user_id)
    update_data = payload.dict(exclude_unset=True)
    
    for attr, value in update_data.items():
        setattr(user, attr, value)
    user.save(update_fields=update_data.keys())
    
    return user

@router.delete("/users/{user_id}", response={204: None})
def delete_user(request, user_id: int):
    """Eliminación (SOLO PARA SUPERADMINS)"""
    if not request.user.is_superuser:
        raise HttpError(403, "Solo un superadministrador puede eliminar cuentas globales.")
        
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return 204, None

# Endpoint para que un Admin de marca cree un empleado vinculado a su empresa
@router.post("/brand/employees", response={201: UserOut})
def create_brand_employee(
    request, 
    payload: EmployeeCreateInput, 
    x_brand_id: int = Header(..., alias="X-Brand-Id")
):
    """
    Invita a un usuario a la marca. Si el usuario no existe en el sistema, lo crea.
    """
    tenant = get_current_tenant(request, x_brand_id)
    active_brand = tenant.brand

    try:
        role = Role.objects.get(id=payload.role_id) 
    except Role.DoesNotExist:
        raise HttpError(400, "El rol especificado no existe en el sistema.")

    try:
        with transaction.atomic():
            
            # 1. ¿El usuario ya existe en nuestro SaaS?
            user = User.objects.filter(email=payload.email).first()
            
            if not user:
                # ESCENARIO A: El usuario es totalmente nuevo
                user = User.objects.create_user(
                    email=payload.email,
                    password=payload.password, # Solo usamos el password temporal si es nuevo
                    first_name=payload.first_name,
                    last_name=payload.last_name,
                )

                # Creamos su perfil de una vez
                profile, _ = UserProfile.objects.get_or_create(user=user)
                if payload.document_id: profile.document_id = payload.document_id
                if payload.phone: profile.phone = payload.phone
                if payload.address: profile.address = payload.address
                profile.save()
                
            else:
                # ESCENARIO B: El usuario ya existe (tiene cuenta en Trato)
                # Verificamos que no esté ya vinculado a esta misma empresa
                if BrandUser.objects.filter(user=user, brand=active_brand).exists():
                    # Si quieres ser fancy, aquí podrías actualizarle el rol en lugar de lanzar error, 
                    # pero lanzar error es más seguro para evitar cambios accidentales.
                    raise HttpError(400, "Este usuario ya pertenece a tu empresa.")
                
                # Opcional: Podrías actualizar su nombre/apellido si quieres, 
                # pero generalmente se respeta la data que el usuario ya tenía.

            # 2. Vincular el Usuario a la Marca (Sea nuevo o existente)
            BrandUser.objects.create(
                user=user,
                brand=active_brand,
                role=role
            )
            
            return 201, user

    except HttpError:
        raise # Dejamos pasar los errores 400 que nosotros mismos lanzamos
    except Exception as e:
        raise HttpError(400, f"Error al vincular el empleado: {str(e)}")