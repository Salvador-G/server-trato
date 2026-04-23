```python
from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL

# =========================
# BRAND (Tenant / Marca SaaS)
# =========================
class Brand(models.Model):
    name = models.CharField(max_length=150, verbose_name="Nombre Comercial")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand"
        verbose_name_plural = "Brands"

    def __str__(self):
        return self.name
    
# =========================
# BRAND LEGAL PROFILE
# =========================
class BrandLegalProfile(models.Model):
    brand = models.OneToOneField(
        Brand, 
        on_delete=models.CASCADE, 
        related_name="legal_profile"
    )
    tax_id = models.CharField(
        max_length=50, 
        unique=True, # ¡Blindaje! Dos marcas no pueden usar el mismo RUC para pagar el SaaS
        verbose_name="RUC / ID Fiscal"
    )
    legal_name = models.CharField(max_length=255, verbose_name="Razón Social")
    fiscal_address = models.TextField(blank=True, null=True, verbose_name="Dirección Fiscal")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Brand Legal Profile"
        verbose_name_plural = "Brand Legal Profiles"

    def __str__(self):
        return f"{self.legal_name} ({self.tax_id})"

# =========================
# PERMISSION (Diccionario Global de Permisos)
# =========================
class Permission(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text="Ej: trade.contact, contract.generate"
    )
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "Permission"
        verbose_name_plural = "Permissions"

    def __str__(self):
        return self.code

# =========================
# ROLE (Aislado por Marca)
# =========================
class Role(models.Model):
    # ¡CLAVE SAAS! El rol pertenece a una marca específica
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="roles") 
    
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    # Crea la tabla pivot: role_permission automáticamente
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Una misma marca no puede tener dos roles que se llamen igual
        unique_together = ("brand", "name") 
        verbose_name = "Role"
        verbose_name_plural = "Roles"

    def __str__(self):
        return f"{self.name} ({self.brand.name})"

# =========================
# BRAND_USER (Pivot: Trabajador ↔ Marca ↔ Rol)
# =========================
class BrandUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="brand_roles")
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, related_name="users")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)

    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments_created"
    )

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("user", "brand")
        verbose_name = "Brand User"
        verbose_name_plural = "Brand Users"

    def __str__(self):
        return f"{self.user} @ {self.brand} ({self.role.name})"


# core/schemas.py
from ninja import ModelSchema, Schema
from typing import List, Optional
from datetime import datetime
from .models import Brand, BrandLegalProfile, Permission, Role, BrandUser

# =========================
# SCHEMAS: BRAND LEGAL PROFILE (KYC)
# =========================
class BrandLegalProfileOut(ModelSchema):
    class Meta:
        model = BrandLegalProfile
        fields = ['tax_id', 'legal_name', 'fiscal_address']

class BrandLegalProfileUpdate(ModelSchema):
    # Todos son opcionales para que puedan actualizar un dato a la vez con PATCH
    tax_id: Optional[str] = None
    legal_name: Optional[str] = None
    fiscal_address: Optional[str] = None
    
    class Meta:
        model = BrandLegalProfile
        fields = ['tax_id', 'legal_name', 'fiscal_address']
        config = {"extra": "ignore"}
        
# =========================
# SCHEMAS: BRAND
# =========================
class BrandOut(ModelSchema):
    legal_profile: Optional[BrandLegalProfileOut] = None# Anidamos el perfil legal dentro del brand
    
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

class UserMeOut(Schema):
    full_name: str
    role_name: str
    avatar_url: Optional[str] = None # Por ahora puede ser null
    
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


# core/utils/email_receiver.py
import imaplib
import email
import email.utils
from email.header import decode_header
from django.utils import timezone
from django.db import transaction
from .encryption import decrypt_password
from communications.models import EmailConfiguration, Message, Conversation
from workflows.models import WorkflowState

def get_decoded_header(header_value):
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = ""
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            result += fragment.decode(encoding or 'utf-8', errors='ignore')
        else:
            result += fragment
    return result

def extract_text_body(msg):
    """
    Extrae ÚNICAMENTE el texto del correo, ignorando logos en firmas, 
    documentos adjuntos y basura HTML pesada.
    """
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            # Ignoramos cualquier parte que sea un archivo adjunto
            if part.get('Content-Disposition') is not None:
                continue
                
            content_type = part.get_content_type()
            
            # Priorizamos texto plano por limpieza del CRM
            if content_type == "text/plain":
                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break # Encontramos el texto, salimos del loop para no procesar imágenes
            
            # Si no hay texto plano, intentamos rescatar el HTML
            elif content_type == "text/html" and not body:
                raw_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                # Aquí podrías usar librerías como BeautifulSoup para limpiar el HTML, 
                # pero por ahora lo guardamos en crudo.
                body = raw_html
    else:
        # Correo simple sin partes
        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
    return body.strip()

def fetch_unread_emails():
    configs = EmailConfiguration.objects.filter(is_active=True)
    
    for config in configs:
        try:
            password = decrypt_password(config.imap_password)
            if config.use_ssl:
                mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
            else:
                mail = imaplib.IMAP4(config.imap_host, config.imap_port)
            
            mail.login(config.imap_username, password)
            mail.select('inbox')
            
            status, response = mail.search(None, 'UNSEEN')
            unread_msg_nums = response[0].split()
            
            for num in unread_msg_nums:
                status, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject = get_decoded_header(msg.get("Subject"))
                        raw_from = get_decoded_header(msg.get("From"))
                        
                        # === MAGIA AQUÍ: Extraemos SOLO el correo limpio ===
                        real_name, pure_email = email.utils.parseaddr(raw_from)
                        
                        print(f"\n[NUEVO CORREO] De: {pure_email} | Asunto: {subject}")

                        body = extract_text_body(msg)

                        # Buscamos usando el correo EXACTO y limpio
                        conversations = Conversation.objects.filter(
                            customer_workflow__customer__contact__email__iexact=pure_email,
                            channel='email'
                        ).order_by('-updated_at')

                        if conversations.exists():
                            Message.objects.create(
                                conversation=conversations.first(),
                                direction='inbound',
                                subject=subject,
                                body=body,
                                from_address=pure_email, # Guardamos el limpio
                                to_address=config.email_address,
                                status='delivered',
                                received_at=timezone.now()
                            )
                            print("[ÉXITO] Mensaje guardado y vinculado al CRM.")
                        else:
                            print(f"[ERROR] No hay oportunidad activa para el cliente {pure_email}.")
            mail.logout()
        except Exception as e:
            print(f"\n[ERROR CRÍTICO en {config.email_address}]: {str(e)}")
            
def fetch_unread_emails():
    configs = EmailConfiguration.objects.filter(is_active=True)
    
    for config in configs:
        try:
            password = decrypt_password(config.imap_password)
            if config.use_ssl:
                mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
            else:
                mail = imaplib.IMAP4(config.imap_host, config.imap_port)
            
            mail.login(config.imap_username, password)
            mail.select('inbox')
            
            status, response = mail.search(None, 'UNSEEN')
            unread_msg_nums = response[0].split()
            
            for num in unread_msg_nums:
                status, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject = get_decoded_header(msg.get("Subject"))
                        raw_from = get_decoded_header(msg.get("From"))
                        
                        real_name, pure_email = email.utils.parseaddr(raw_from)
                        
                        print(f"\n[NUEVO CORREO] De: {pure_email} | Asunto: {subject}")

                        body = extract_text_body(msg)

                        conversations = Conversation.objects.filter(
                            customer_workflow__customer__contact__email__iexact=pure_email,
                            channel='email'
                        ).order_by('-updated_at')

                        if conversations.exists():
                            conversation = conversations.first()
                            workflow = conversation.customer_workflow
                            
                            with transaction.atomic():
                                # 1. Guardar el correo
                                Message.objects.create(
                                    conversation=conversation,
                                    direction='inbound',
                                    subject=subject,
                                    body=body,
                                    from_address=pure_email,
                                    to_address=config.email_address,
                                    status='delivered',
                                    received_at=timezone.now()
                                )
                                print(f"[ÉXITO] Mensaje guardado y vinculado al CRM para {pure_email}.")

                                # 2. Avanzar el pipeline a Negociación de forma SEGURA usando el 'code'
                                # Solo avanzamos si el workflow pertenece a Trade y está en el primer paso (lead/prospecto)
                                if workflow.workflow.code == 'trade' and workflow.current_state.code == 'lead':
                                    try:
                                        # Buscamos el estado por su CODE, no por su nombre.
                                        estado_negociacion = WorkflowState.objects.get(
                                            code='negotiation', 
                                            workflow=workflow.workflow
                                        )
                                        
                                        # Actualizamos el estado
                                        workflow.current_state = estado_negociacion
                                        workflow.save()
                                        
                                        # OPCIONAL PERO RECOMENDADO: Registrar en el historial de cambios
                                        from workflows.models import CustomerWorkflowHistory
                                        CustomerWorkflowHistory.objects.create(
                                            customer_workflow=workflow,
                                            state=estado_negociacion,
                                            user=None, # System/Auto
                                            comment="Cambiado automáticamente a Negociación tras recibir correo del cliente."
                                        )
                                        
                                        print(f"[PIPELINE] Trade {workflow.id} avanzado a Negociación automáticamente.")
                                    
                                    except WorkflowState.DoesNotExist:
                                        print(f"[ERROR CRÍTICO] No se encontró el estado con código 'negotiation' para el workflow {workflow.workflow.id}")
                        else:
                            print(f"[ERROR] No hay oportunidad activa para el cliente {pure_email}.")
            mail.logout()
        except Exception as e:
            print(f"\n[ERROR CRÍTICO en {config.email_address}]: {str(e)}")


# core/utils/email_sender.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .encryption import decrypt_password

def send_dynamic_email(email_config, to_address: str, subject: str, body: str, from_header: str):
    """
    Se conecta al SMTP del cliente, desencripta su contraseña y envía el correo real.
    Devuelve (True, None) si fue exitoso, o (False, error_msg) si falló.
    """
    # 1. Armamos el paquete del correo
    msg = MIMEMultipart()
    msg['From'] = from_header
    msg['To'] = to_address
    msg['Subject'] = subject or "Sin Asunto"
    msg.attach(MIMEText(body, 'plain')) # Si usas un editor rico en el frontend, cambia 'plain' por 'html'

    # 2. Desencriptamos la contraseña
    plain_password = decrypt_password(email_config.smtp_password)

    # 3. Nos conectamos y enviamos
    try:
        # === ¡CAMBIO CLAVE AQUÍ! ===
        if email_config.smtp_port == 465:
            # El puerto 465 requiere conexión segura inmediata (SMTP_SSL)
            server = smtplib.SMTP_SSL(email_config.smtp_host, email_config.smtp_port)
        else:
            # El puerto 587 u otros usan conexión normal y luego starttls()
            server = smtplib.SMTP(email_config.smtp_host, email_config.smtp_port)
            if email_config.use_tls:
                server.starttls()
                
        # Iniciamos sesión y disparamos
        server.login(email_config.smtp_username, plain_password)
        server.send_message(msg)
        server.quit()
        
        return True, None
    except Exception as e:
        # Capturamos si la contraseña está mal, si el puerto está bloqueado, etc.
        return False, str(e)


# core/utils/encryption.py
import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings

def get_fernet():
    """Deriva una llave válida de 32-bytes a partir del SECRET_KEY de Django"""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)

def encrypt_password(plain_text: str) -> str:
    if not plain_text:
        return ""
    return get_fernet().encrypt(plain_text.encode()).decode()

def decrypt_password(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        return get_fernet().decrypt(cipher_text.encode()).decode()
    except Exception:
        return ""
```