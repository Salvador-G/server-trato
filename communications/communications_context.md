# communications/models.py

```python
from django.db import models

# =========================
# EMAIL CONFIGURATION (BYOE)
# =========================
class EmailConfiguration(models.Model):
    brand = models.ForeignKey(
        "core.Brand", 
        on_delete=models.CASCADE, 
        related_name="email_configs"
    )
    email_address = models.EmailField(verbose_name="Dirección de Correo (Ej: ventas@marca.com)")
    
    # --- DATOS SMTP (Envío) ---
    smtp_host = models.CharField(max_length=255, verbose_name="Host SMTP")
    smtp_port = models.IntegerField(default=587, verbose_name="Puerto SMTP")
    smtp_username = models.CharField(max_length=255, verbose_name="Usuario SMTP")
    smtp_password = models.CharField(max_length=500, verbose_name="Contraseña SMTP (Encriptada)")
    use_tls = models.BooleanField(default=True)

    # --- DATOS IMAP (Recepción) ---
    imap_host = models.CharField(max_length=255, verbose_name="Host IMAP")
    imap_port = models.IntegerField(default=993, verbose_name="Puerto IMAP")
    imap_username = models.CharField(max_length=255, verbose_name="Usuario IMAP")
    imap_password = models.CharField(max_length=500, verbose_name="Contraseña IMAP (Encriptada)")
    use_ssl = models.BooleanField(default=True)

    # --- SEGURIDAD ---
    daily_send_limit = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Email Configuration"
        verbose_name_plural = "Email Configurations"
        unique_together = ("brand", "email_address")

    def __str__(self):
        return f"{self.email_address} ({self.brand.name})"


# =========================
# CONVERSATION (El hilo o "Ticket")
# =========================
class Conversation(models.Model):
    CHANNEL_CHOICES = (
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'), 
        ('sms', 'SMS'),
    )

    customer_workflow = models.ForeignKey(
        "workflows.CustomerWorkflow", 
        on_delete=models.CASCADE, 
        related_name="conversations",
        verbose_name="Proceso del Cliente"
    )
    
    channel = models.CharField(
        max_length=20, 
        choices=CHANNEL_CHOICES, 
        default='email',
        verbose_name="Canal de Comunicación"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversación #{self.id} ({self.get_channel_display()}) - {self.customer_workflow}"


# =========================
# MESSAGE (El mensaje Omnicanal)
# =========================
class Message(models.Model):
    DIRECTION_CHOICES = (
        ('inbound', 'Entrante (Del cliente)'),
        ('outbound', 'Saliente (Hacia el cliente)'),
    )
    
    STATUS_CHOICES = (
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
        ('delivered', 'Entregado'),
        ('read', 'Leído'),
        ('error', 'Error de envío'),
    )

    conversation = models.ForeignKey(
        Conversation, 
        on_delete=models.CASCADE, 
        related_name="messages",
        verbose_name="Hilo de Conversación"
    )
    
    direction = models.CharField(max_length=15, choices=DIRECTION_CHOICES, verbose_name="Dirección")
    subject = models.CharField(max_length=255, blank=True, null=True, verbose_name="Asunto")
    body = models.TextField(verbose_name="Cuerpo del mensaje")
    
    from_address = models.CharField(max_length=255, verbose_name="De (Remitente / Teléfono)")
    to_address = models.CharField(max_length=255, verbose_name="Para (Destinatario / Teléfono)")
    
    provider_message_id = models.CharField(max_length=255, blank=True, verbose_name="ID del Proveedor (SendGrid/Meta)")
    in_reply_to = models.CharField(max_length=255, blank=True, verbose_name="En respuesta a (ID)")
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft', verbose_name="Estado")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadata Omnicanal")
    
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Enviado el")
    received_at = models.DateTimeField(null=True, blank=True, verbose_name="Recibido el")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_direction_display()} - {self.subject or 'Sin Asunto'} ({self.status})"


# =========================
# MESSAGE ATTACHMENT (Adjuntos)
# =========================
class MessageAttachment(models.Model):
    message = models.ForeignKey(
        Message, 
        on_delete=models.CASCADE, 
        related_name="attachments",
        verbose_name="Mensaje"
    )
    
    file = models.FileField(
        upload_to="attachments/%Y/%m/", 
        verbose_name="Archivo Adjunto"
    )
    
    mime_type = models.CharField(max_length=100, blank=True, verbose_name="MIME Type")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message Attachment"
        verbose_name_plural = "Message Attachments"

    def __str__(self):
        return self.file.name.split('/')[-1] if self.file else "Adjunto vacío"
```

# communications/schemas.py

```python
from ninja import ModelSchema, Schema
from typing import List, Optional
from .models import EmailConfiguration, Conversation, Message, MessageAttachment

# =========================
# EMAIL CONFIGURATION (BYOE)
# =========================
class EmailConfigOut(ModelSchema):
    class Meta:
        model = EmailConfiguration
        fields = [
            'id', 'email_address', 'smtp_host', 'smtp_port', 'smtp_username', 'use_tls',
            'imap_host', 'imap_port', 'imap_username', 'use_ssl', 'is_active'
        ]

class EmailConfigCreate(Schema):
    email_address: str
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str
    use_tls: bool = True
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str
    use_ssl: bool = True


# =========================
# CONVERSACIONES Y MENSAJES
# =========================
class MessageAttachmentOut(ModelSchema):
    file_url: Optional[str] = None

    class Meta:
        model = MessageAttachment
        fields = ['id', 'mime_type', 'created_at']

    @staticmethod
    def resolve_file_url(obj: MessageAttachment) -> Optional[str]:
        return obj.file.url if obj.file else None


class MessageOut(ModelSchema):
    attachments: List[MessageAttachmentOut] = []

    class Meta:
        model = Message
        fields = [
            'id', 'direction', 'subject', 'body', 'from_address', 
            'to_address', 'status', 'sent_at', 'created_at'
        ]


class ConversationOut(ModelSchema):
    customer_workflow_id: int

    class Meta:
        model = Conversation
        fields = ['id', 'channel', 'created_at', 'updated_at']


class SendMessagePayload(Schema):
    customer_workflow_id: int
    channel: str
    body: str
    subject: Optional[str] = None
    to_address: str
```

# communications/routers.py

```python
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from ninja_jwt.authentication import JWTAuth

from .models import EmailConfiguration, Conversation, Message
from .schemas import (
    EmailConfigOut, EmailConfigCreate, 
    ConversationOut, MessageOut, SendMessagePayload
)
from workflows.models import CustomerWorkflow, CustomerWorkflowHistory
from core.dependencies import get_current_tenant
from core.utils.encryption import encrypt_password
from core.utils.email_sender import send_dynamic_email

router = Router(tags=["Communications"], auth=JWTAuth())


# ==========================================
# CONFIGURACIÓN DE CORREOS (BYOE)
# ==========================================

@router.get("/email-configs", response=List[EmailConfigOut])
def list_email_configs(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    return EmailConfiguration.objects.filter(brand=tenant.brand)


@router.post("/email-configs", response={201: EmailConfigOut})
def create_email_config(request, payload: EmailConfigCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    encrypted_smtp = encrypt_password(payload.smtp_password)
    encrypted_imap = encrypt_password(payload.imap_password)
    
    config, created = EmailConfiguration.objects.update_or_create(
        brand=tenant.brand,
        email_address=payload.email_address,
        defaults={
            'smtp_host': payload.smtp_host,
            'smtp_port': payload.smtp_port,
            'smtp_username': payload.smtp_username,
            'smtp_password': encrypted_smtp,
            'use_tls': payload.use_tls,
            'imap_host': payload.imap_host,
            'imap_port': payload.imap_port,
            'imap_username': payload.imap_username,
            'imap_password': encrypted_imap,
            'use_ssl': payload.use_ssl,
            'is_active': True
        }
    )
    return 201, config


# ==========================================
# CHATS Y MENSAJES
# ==========================================

@router.get("/workflows/{cw_id}/conversations", response=List[ConversationOut])
def list_conversations(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand)
    return Conversation.objects.filter(customer_workflow=cw)


@router.get("/conversations/{conversation_id}/messages", response=List[MessageOut])
def list_messages(request, conversation_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    conversation = get_object_or_404(
        Conversation, 
        id=conversation_id, 
        customer_workflow__workflow__brand=tenant.brand
    )
    return Message.objects.filter(conversation=conversation).prefetch_related('attachments')


@router.post("/messages/send", response={201: MessageOut})
def send_message(request, payload: SendMessagePayload, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    with transaction.atomic():
        try:
            cw = CustomerWorkflow.objects.select_for_update(nowait=False).get(
                id=payload.customer_workflow_id, 
                workflow__brand=tenant.brand
            )
        except CustomerWorkflow.DoesNotExist:
            raise HttpError(404, "Proceso no encontrado")

        if cw.assigned_to is None:
            cw.assigned_to = request.user
            cw.save()
            
            CustomerWorkflowHistory.objects.create(
                customer_workflow=cw,
                state=cw.current_state,
                user=request.user,
                comment="Lead tomado automáticamente por primera interacción."
            )

        elif cw.assigned_to != request.user:
            dueño = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email
            raise HttpError(
                403, 
                f"Este lead ya está siendo atendido por {dueño}. No puedes enviarle mensajes."
            )

        if payload.channel == 'email':
            email_config = cw.workflow.email_config
            
            if not email_config:
                raise HttpError(
                    400, 
                    f"El proceso '{cw.workflow.name}' no tiene una bandeja de correo configurada."
                )
            
            sender_name = (
                f"{request.user.first_name} {request.user.last_name}".strip()
                or f"Equipo de {cw.workflow.name}"
            )
            
            from_address = f"{sender_name} <{email_config.email_address}>"

        else:
            from_address = "WhatsApp API"

        conversation, _ = Conversation.objects.get_or_create(
            customer_workflow=cw, 
            channel=payload.channel
        )

        msg = Message.objects.create(
            conversation=conversation,
            direction='outbound',
            subject=payload.subject,
            body=payload.body,
            to_address=payload.to_address,
            from_address=from_address, 
            status='draft'
        )
        
        if payload.channel == 'email':
            success, error_msg = send_dynamic_email(
                email_config=email_config,
                to_address=payload.to_address,
                subject=payload.subject,
                body=payload.body,
                from_header=from_address
            )
            
            if success:
                msg.status = 'sent'
                msg.sent_at = timezone.now()
            else:
                msg.status = 'error'
                msg.metadata = {"error_detail": error_msg}
                
            msg.save()

    return 201, msg
```