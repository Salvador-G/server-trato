# accounts/routers.py
from ninja import Router, Schema
from django.db import transaction
from django.contrib.auth.models import update_last_login
from ninja.errors import HttpError
from typing import List
from django.contrib.auth import get_user_model, authenticate
from django.shortcuts import get_object_or_404
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.tokens import RefreshToken
from core.utils.audit import log_audit_event
from core.utils.network import get_client_ip, rate_limit

from core.models import Brand, BrandUser, Role
from .schemas import AdminUserUpdate, UserOut, UserCreate, UserUpdate, EmployeeCreateInput
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
def create_brand_employee(request, payload: EmployeeCreateInput):
    """
    Crea un empleado y lo vincula a la marca del administrador que hace la petición.
    """
    # 1. Obtener el contexto de la marca del Admin actual.
    # Asumimos que tienes una forma de saber en qué marca está operando el admin.
    # Por ejemplo, obteniendo su registro de BrandUser:
    admin_brand_link = BrandUser.objects.filter(user=request.user, is_active=True).first()
    if not admin_brand_link:
        raise HttpError(403, "El usuario actual no pertenece a ninguna marca activa.")
    
    active_brand = admin_brand_link.brand

    # 2. Validar que el Role especificado pertenece a ESTA marca
    # Esto evita que un admin asigne un rol global o de otra empresa.
    try:
        role = Role.objects.get(id=payload.role_id, brand=active_brand)
    except Role.DoesNotExist:
        raise HttpError(400, "El rol especificado no existe en tu empresa.")

    # 3. Transacción Atómica: O se crea todo, o no se crea nada
    try:
        with transaction.atomic():
            # A) Crear el Usuario Global
            new_user = User.objects.create_user(
                email=payload.email,
                password=payload.password,
                first_name=payload.first_name,
                last_name=payload.last_name
            )

            # B) Crear o Actualizar el UserProfile (si usaste signals, esto lo actualiza)
            # Usamos get_or_create por si la señal post_save ya lo creó vacío
            profile, created = UserProfile.objects.get_or_create(user=new_user)
            if payload.document_id:
                profile.document_id = payload.document_id
            if payload.phone:
                profile.phone = payload.phone
            if payload.address:
                profile.address = payload.address
            profile.save()

            # C) Vincular el Usuario a la Marca con su Rol (BrandUser)
            BrandUser.objects.create(
                user=new_user,
                brand=active_brand,
                role=role
            )
            
            return 201, new_user

    except Exception as e:
        # Aquí puedes loggear el error real para ti
        raise HttpError(400, f"Error al crear el empleado: {str(e)}")