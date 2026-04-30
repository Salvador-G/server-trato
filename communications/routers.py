# communications/routers.py
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
from workflows.models import CustomerWorkflow, CustomerWorkflowHistory, WorkflowState
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
    conversation = get_object_or_404(Conversation, id=conversation_id, customer_workflow__workflow__brand=tenant.brand)
    return Message.objects.filter(conversation=conversation).prefetch_related('attachments')

@router.post("/messages/send", response={201: MessageOut})
def send_message(request, payload: SendMessagePayload, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    with transaction.atomic():
        # 1. BLOQUEO ANTI-COLISIÓN
        try:
            cw = CustomerWorkflow.objects.select_for_update(nowait=False).get(
                id=payload.customer_workflow_id, 
                workflow__brand=tenant.brand
            )
        except CustomerWorkflow.DoesNotExist:
            raise HttpError(404, "Proceso no encontrado")

        # 2. REGLAS DE ASIGNACIÓN
        if cw.assigned_to is None:
            # Auto-asignar al primer valiente que responde
            cw.assigned_to = request.user
            cw.save()
            
            CustomerWorkflowHistory.objects.create(
                customer_workflow=cw,
                state=cw.current_state,
                user=request.user,
                comment=f"Lead tomado automáticamente por primera interacción."
            )
        elif cw.assigned_to != request.user:
            # Prevenir que otro asesor se meta si ya tiene dueño
            dueño = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email
            raise HttpError(403, f"Este lead ya está siendo atendido por {dueño}. No puedes enviarle mensajes.")

        # 3. LÓGICA DE ENVÍO ORIGINAL
        if payload.channel == 'email':
            email_config = cw.workflow.email_config
            if not email_config:
                raise HttpError(400, f"El proceso '{cw.workflow.name}' no tiene una bandeja de correo configurada.")
            
            sender_name = f"{request.user.first_name} {request.user.last_name}".strip() or f"Equipo de {cw.workflow.name}"
            from_address = f"{sender_name} <{email_config.email_address}>"
        else:
            from_address = "WhatsApp API"

        conversation, _ = Conversation.objects.get_or_create(customer_workflow=cw, channel=payload.channel)

        msg = Message.objects.create(
            conversation=conversation,
            direction='outbound',
            subject=payload.subject,
            body=payload.body,
            to_address=payload.to_address,
            from_address=from_address, 
            status='draft', 
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
                
                # ==========================================
                # NUEVO: TRANSICIÓN AUTOMÁTICA DE ESTADO
                # ==========================================
                if payload.advance_state_to:
                    try:
                        new_state = WorkflowState.objects.get(
                            workflow=cw.workflow, 
                            code=payload.advance_state_to
                        )
                        # Solo avanzamos si realmente es un estado diferente
                        if cw.current_state != new_state:
                            cw.current_state = new_state
                            cw.save()
                            
                            CustomerWorkflowHistory.objects.create(
                                customer_workflow=cw,
                                state=new_state,
                                user=request.user,
                                comment=f"Fase avanzada a '{new_state.name}' tras enviar documento/correo."
                            )
                    except WorkflowState.DoesNotExist:
                        # Si envían un código inválido, lo ignoramos para no romper el envío del correo
                        pass

            else:
                msg.status = 'error'
                msg.metadata = {"error_detail": error_msg} 
                
        msg.save()

    return 201, msg