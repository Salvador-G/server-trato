# modules_api/routers/support.py
from ninja import Router, Header
from ninja_jwt.authentication import JWTAuth
from typing import List
from itertools import chain

from django.conf import settings
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string
from ninja.errors import HttpError

from communications.models import Message
from workflows.models import WorkflowState, CustomerWorkflow, CustomerWorkflowHistory
from core.dependencies import get_current_tenant
from ..schemas import SupportListRowOut, TradeMainOut

router = Router(tags=["Modules API - Support (Operaciones/Onboarding)"], auth=JWTAuth())
User = get_user_model()

@router.get("/active", response=List[SupportListRowOut])
def list_active_support(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de clientes en proceso de Onboarding.
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    cws = CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='support', # <-- Código del flujo de soporte
        finished_at__isnull=True
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-started_at')

    resultados = []
    for cw in cws:
        cliente = cw.customer
        empresa = cliente.company
        
        ruc = empresa.tax_id if empresa else "N/A"
        razon_social = empresa.legal_name if empresa else (cliente.contact.full_name if cliente.contact else "Sin Nombre")
        personal = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() if cw.assigned_to else "Sin asignar"

        resultados.append({
            "id": cw.id,
            "fecha": cw.started_at,
            "ruc": ruc,
            "razonSocial": razon_social,
            "personal": personal,
            "estadoId": cw.current_state.code 
        })

    return resultados

@router.get("/active/{cw_id}/main", response=TradeMainOut)
def get_support_main_data(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    cw = get_object_or_404(
        CustomerWorkflow.objects.select_related('workflow', 'current_state', 'customer__contact'), 
        id=cw_id, 
        workflow__brand=tenant.brand,
        workflow__code='support'
    )

    contact_email = cw.customer.contact.email if cw.customer.contact else ""
    
    # --- PIPELINE DE PASOS ---
    historial_pasos = []
    current_order = cw.current_state.sort_order
    all_states = cw.workflow.states.all().order_by('sort_order')
    history_logs = list(cw.history_logs.all())
    history_dates = {log.state_id: log.changed_at for log in sorted(history_logs, key=lambda x: x.changed_at)}

    for state in all_states:
        historial_pasos.append({
            "nombre": state.name,
            "estado": "completado" if state.sort_order <= current_order else "pendiente",
            "fecha": history_dates.get(state.id, None), 
            "tipo": "envio" 
        })

    # --- HISTORIAL OMNICANAL ---
    history_events = []
    # AÑADIDO: prefetch_related
    messages = Message.objects.filter(
        conversation__customer_workflow=cw
    ).select_related('conversation').prefetch_related('attachments__document')

    combined_timeline = sorted(
        chain(history_logs, messages),
        key=lambda obj: obj.changed_at if hasattr(obj, 'changed_at') else obj.created_at,
        reverse=True
    )

    for item in combined_timeline:
        if hasattr(item, 'state'):
            color = "#10b981" if item.state.is_final else "#d1d5db"
            history_events.append({
                "status": f"Fase: {item.state.name}",
                "description": item.comment or "Actualización de soporte.",
                "date": item.changed_at, "color": color
            })
        else:
            is_inbound = item.direction == 'inbound'
            color = "#f59e0b" if is_inbound else "#06b6d4" # Cyan para soporte
            
            # AÑADIDO: Lógica de extracción de adjuntos
            attachments_data = []
            if hasattr(item, 'attachments'):
                for att in item.attachments.all():
                    if att.document and att.document.file:
                        filename = att.document.original_filename or os.path.basename(att.document.file.name)
                        attachments_data.append({
                            "id": att.id,
                            "url": att.document.file.url,
                            "name": filename
                        })

            history_events.append({
                "status": "Respuesta de cliente" if is_inbound else "Correo/Credenciales enviadas",
                "description": f"Asunto: {item.subject or 'Sin asunto'}",
                "body": getattr(item, 'body', None),
                "date": item.created_at, 
                "color": color,
                "attachments": attachments_data # <-- PASAMOS LOS ADJUNTOS
            })

    # --- REDACTAR CORREO ---
    esperando_respuesta = cw.current_state.code == 'waiting_setup' 
    email_draft = {
        "to": contact_email,
        "subject": "¡Bienvenido! Aquí están tus accesos",
        "body": "Estimados,\n\nSu cuenta ha sido aprovisionada con éxito. Pueden acceder a la plataforma utilizando el siguiente enlace temporal para configurar su contraseña:\n\n[ENLACE_DE_ACCESO]\n\nAtentamente,\nEl Equipo de Soporte."
    }

    assigned_name = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() if cw.assigned_to else None

    return {
        "customer_id": cw.customer.id,
        "esperandoRespuesta": esperando_respuesta,
        "historialPasos": historial_pasos,
        "historyEvents": history_events,
        "emailDraft": email_draft,
        "assigned_to_id": cw.assigned_to_id,
        "assigned_to_name": assigned_name,
        "current_user_id": request.user.id
    }

# ==========================================
# ACCIONES DE BOTONES (El Interruptor)
# ==========================================

@router.post("/active/{cw_id}/generate-access")
def generate_credentials(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand, workflow__code='support', finished_at__isnull=True)

    if cw.assigned_to_id and cw.assigned_to_id != request.user.id:
        raise HttpError(403, "No puedes generar acceso porque está asignado a otro operador.")

    # 1. Lógica de creación de usuario (Generación de contraseña o Magic Link)
    contact_email = cw.customer.contact.email
    temporal_password = get_random_string(12)
    
    user, created = User.objects.get_or_create(
        email=contact_email,
        defaults={
            'first_name': cw.customer.contact.first_name,
            'last_name': cw.customer.contact.last_name,
            'is_active': True 
        }
    )
    if created:
        user.set_password(temporal_password)
        user.save()
        mensaje_historial = f"Usuario creado y credenciales enviadas a {contact_email}."
    else:
        mensaje_historial = f"El usuario {contact_email} ya existía. Accesos actualizados."

    # 2. EL INTERRUPTOR DE FLUJO
    # Si REQUIRE_MANUAL_ACTIVATION no está definido en settings, asume True por seguridad.
    requiere_activacion_manual = getattr(settings, 'REQUIRE_MANUAL_ACTIVATION', True)

    if requiere_activacion_manual:
        # Esperamos a que el cliente configure y Soporte presione "Activar Servicio"
        try:
            waiting_state = WorkflowState.objects.get(workflow=cw.workflow, code='waiting_setup')
        except WorkflowState.DoesNotExist:
            raise HttpError(400, "El estado 'waiting_setup' no existe en el flujo.")
            
        cw.current_state = waiting_state
        cw.save()
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=cw, state=waiting_state, user=request.user, 
            comment=mensaje_historial + " Esperando configuración del cliente."
        )
        return {"success": True, "message": "Accesos generados. Esperando activación manual."}

    else:
        # Auto-Activación: Pasamos directo al final
        try:
            final_state = WorkflowState.objects.get(workflow=cw.workflow, code='live')
        except WorkflowState.DoesNotExist:
            raise HttpError(400, "El estado 'live' no existe en el flujo.")
            
        cw.current_state = final_state
        cw.finished_at = timezone.now()
        cw.save()
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=cw, state=final_state, user=request.user, 
            comment=mensaje_historial + " Auto-activado (Interruptor global). Fin del Onboarding."
        )
        return {"success": True, "message": "Accesos generados y servicio activado automáticamente."}


@router.post("/active/{cw_id}/activate-service")
def activate_service(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Solo se utiliza si REQUIRE_MANUAL_ACTIVATION = True.
    """
    tenant = get_current_tenant(request, x_brand_id)
    cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand, workflow__code='support', finished_at__isnull=True)

    if cw.assigned_to_id and cw.assigned_to_id != request.user.id:
        raise HttpError(403, "No puedes activar este servicio porque está asignado a otro operador.")

    try:
        final_state = WorkflowState.objects.get(workflow=cw.workflow, code='live')
    except WorkflowState.DoesNotExist:
        raise HttpError(400, "El estado final 'live' no existe en el flujo.")

    cw.current_state = final_state
    cw.finished_at = timezone.now()
    cw.save()

    CustomerWorkflowHistory.objects.create(
        customer_workflow=cw, state=final_state, user=request.user, 
        comment="Servicio activado manualmente. Fin del Onboarding."
    )

    return {"success": True, "message": "Servicio activado. El cliente ya tiene acceso total al sistema."}

@router.get("/archived", response=List[SupportListRowOut])
def list_archived_trades(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de tratos finalizados (Ganados o Perdidos).
    Alimentará la vista de historial.
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    # La diferencia clave: finished_at__isnull=False
    cws = CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='support',
        finished_at__isnull=False 
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-finished_at') # Ordenamos por fecha de cierre más reciente

    resultados = []
    
    for cw in cws:
        cliente = cw.customer
        empresa = cliente.company
        
        ruc = empresa.tax_id if empresa else "N/A"
        razon_social = empresa.legal_name if empresa else (cliente.contact.full_name if cliente.contact else "Sin Nombre")
        personal = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() if cw.assigned_to else "Sin asignar"

        resultados.append({
            "id": cw.id,
            "fecha": cw.finished_at, # Ojo: aquí mostramos cuándo se cerró, no cuándo inició
            "ruc": ruc,
            "razonSocial": razon_social,
            "personal": personal,
            "estadoId": cw.current_state.code # Mostrará 'won' (Ganado) o 'lost' (Perdido)
        })

    return resultados