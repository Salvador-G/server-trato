# modules_api/administrator.py
import os
from ninja import Router, Header
from ninja.pagination import paginate, LimitOffsetPagination
from ninja.errors import HttpError
from typing import List
from ninja_jwt.authentication import JWTAuth
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from core.models import BrandUser, AuditLog
from core.dependencies import get_current_tenant, verify_module_access
from ..schemas import AdminUserListOut, UserDetailExtendedOut, AuditLogOut, PasswordResetIn

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
    
# ---------------------------------------------------------
# 4. ALTERAR ESTADO DE LA CUENTA (Suspender / Reactivar)
# ---------------------------------------------------------
@router.patch("/brand/employees/{user_id}/toggle-status", response={200: dict})
def toggle_employee_status(request, user_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    current_tenant = get_current_tenant(request, x_brand_id)
    
    # 1. Verificación de Roles (Solo Owners y Managers)
    if current_tenant.role.name.lower() not in ['owner', 'manager']:
        raise HttpError(403, "No tienes permisos para alterar el estado de los usuarios.")
        
    # 2. Evitar auto-modificación
    if current_tenant.user.id == user_id:
        raise HttpError(400, "No puedes modificar tu propio estado por medidas de seguridad.")

    target_brand_user = get_object_or_404(BrandUser, user_id=user_id, brand=current_tenant.brand)
    
    # Determinamos cuál será el nuevo estado (lo contrario al actual)
    new_status = not target_brand_user.is_active

    # 3. Regla: Protección del último Owner (SOLO si se está intentando suspender)
    if not new_status and target_brand_user.role.name.lower() == 'owner':
        total_owners = BrandUser.objects.filter(brand=current_tenant.brand, role__name__iexact='owner', is_active=True).count()
        if total_owners <= 1:
            raise HttpError(400, "No se puede suspender al único Owner activo.")

    # 4. Ejecutar el Toggle Dual
    target_brand_user.is_active = new_status
    target_brand_user.save(update_fields=['is_active'])

    target_user = target_brand_user.user
    target_user.is_active = new_status
    target_user.save(update_fields=['is_active'])

    # 5. Registrar en Auditoría
    accion_log = "USER_REACTIVATED" if new_status else "USER_SUSPENDED"
    AuditLog.objects.create(
        brand=current_tenant.brand,
        actor=current_tenant.user,
        action=accion_log,
        details={"target_user_id": user_id, "target_email": target_user.email}
    )

    mensaje = "Usuario reactivado exitosamente." if new_status else "Usuario suspendido correctamente."
    return 200, {"message": mensaje, "is_active": new_status}

# ---------------------------------------------------------
# 5. RESTABLECER CONTRASEÑA (Tenant Admin)
# ---------------------------------------------------------
@router.post("/brand/employees/{user_id}/reset-password", response={200: dict})
def reset_employee_password(request, user_id: int, payload: PasswordResetIn, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    current_tenant = get_current_tenant(request, x_brand_id)
    
    # 1. Verificación de roles
    if current_tenant.role.name.lower() not in ['Owner', 'Manager']:
        raise HttpError(403, "No tienes permisos para cambiar contraseñas.")

    # 2. Obtener el usuario objetivo
    target_brand_user = get_object_or_404(BrandUser, user_id=user_id, brand=current_tenant.brand)
    target_user = target_brand_user.user

    # 3. Cambiar la contraseña (usamos set_password que encripta automáticamente)
    target_user.set_password(payload.new_password)
    target_user.save(update_fields=['password'])

    # Nota sobre JWT: Cambiar la contraseña en la BD no mata los Access Tokens 
    # que ya están vivos (porque JWT es stateless). Si quieres forzar el logout total 
    # de los dispositivos, necesitarías implementar una Blacklist de tokens en SimpleJWT 
    # y agregar el token actual aquí. Por ahora, el cambio evitará que emitan nuevos tokens.

    # 4. Registrar en Auditoría Operativa
    AuditLog.objects.create(
        brand=current_tenant.brand,
        actor=current_tenant.user,
        action="PASSWORD_RESET",
        details={
            "target_user_id": user_id, 
            "devices_logged_out_requested": payload.logout_devices
        }
    )

    return 200, {"message": "Contraseña actualizada exitosamente."}