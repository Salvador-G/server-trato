# communications/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja_jwt.authentication import JWTAuth

from .models import EmailConfiguration, Conversation, Message
from .schemas import (
    EmailConfigOut, EmailConfigCreate, 
    ConversationOut, MessageOut, SendMessagePayload
)
from workflows.models import CustomerWorkflow
from core.dependencies import get_current_tenant
from core.utils.encryption import encrypt_password
from core.utils.email_sender import send_dynamic_email  # Función hipotética para enviar emails usando smtplib o similar
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
    
    # 1. Encriptamos las contraseñas antes de guardarlas
    encrypted_smtp = encrypt_password(payload.smtp_password)
    encrypted_imap = encrypt_password(payload.imap_password)
    
    # 2. Creamos la configuración
    config = EmailConfiguration.objects.create(
        brand=tenant.brand,
        email_address=payload.email_address,
        smtp_host=payload.smtp_host,
        smtp_port=payload.smtp_port,
        smtp_username=payload.smtp_username,
        smtp_password=encrypted_smtp,
        use_tls=payload.use_tls,
        imap_host=payload.imap_host,
        imap_port=payload.imap_port,
        imap_username=payload.imap_username,
        imap_password=encrypted_imap,
        use_ssl=payload.use_ssl
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
    conversation = get_object_or_404(Conversation, id=conversation_id, customer_workflow__workflow__brand=tenant.brand)
    return Message.objects.filter(conversation=conversation).prefetch_related('attachments')

@router.post("/messages/send", response={201: MessageOut})
def send_message(request, payload: SendMessagePayload, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    cw = get_object_or_404(CustomerWorkflow, id=payload.customer_workflow_id, workflow__brand=tenant.brand)

    # Lógica de Alias Dinámico (Shared Inbox)
    if payload.channel == 'email':
        email_config = cw.workflow.email_config
        if not email_config:
            raise HttpError(400, f"El proceso '{cw.workflow.name}' no tiene una bandeja de correo configurada.")
        
        sender_name = f"{request.user.first_name} {request.user.last_name}" if request.user.first_name else f"Equipo de {cw.workflow.name}"
        from_address = f"{sender_name} <{email_config.email_address}>"
    else:
        from_address = "WhatsApp API"

    # Creamos/Obtenemos el hilo
    conversation, _ = Conversation.objects.get_or_create(customer_workflow=cw, channel=payload.channel)

    # Guardamos en BD inicialmente como 'draft' (por si el envío falla)
    msg = Message.objects.create(
        conversation=conversation,
        direction='outbound',
        subject=payload.subject,
        body=payload.body,
        to_address=payload.to_address,
        from_address=from_address, 
        status='draft', # Empieza como borrador
    )
    
    # === ¡LA MAGIA DEL ENVÍO REAL! ===
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
            msg.metadata = {"error_detail": error_msg} # Guardamos el porqué falló
            
        msg.save()

    return 201, msg