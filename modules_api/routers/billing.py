# modules_api/routers/billing.py
from ninja import Router, Header
from ninja.errors import HttpError
from ninja_jwt.authentication import JWTAuth
from typing import List
from django.utils import timezone
from django.shortcuts import get_object_or_404
from itertools import chain
from communications.models import Message
from workflows.models import CustomerWorkflow, WorkflowState, Workflow, CustomerWorkflowHistory
from core.dependencies import get_current_tenant, verify_module_access
from ..schemas import BillingListRowOut, TradeMainOut

router = Router(tags=["Modules API - Billing (Facturación/Cobranza)"], auth=JWTAuth())

@router.get("/active", response=List[BillingListRowOut])
def list_active_billing(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de flujos de facturación en curso.
    Alimentará la vista de BillingList.vue
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'billing')
    
    # Filtramos: Marca actual, flujo de 'billing', y que no estén finalizados
    return CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='billing', 
        finished_at__isnull=True
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-started_at')

@router.get("/active/{cw_id}/main", response=TradeMainOut)
def get_billing_main_data(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'billing')

    cw = get_object_or_404(
        CustomerWorkflow.objects.select_related(
            'workflow', 'current_state', 'customer__contact'
        ), 
        id=cw_id, 
        workflow__brand=tenant.brand,
        workflow__code='billing' 
    )

    metadata = cw.metadata or {}
    contact_email = cw.customer.contact.email if cw.customer.contact else ""
    
    # --- PIPELINE DE PASOS ---
    historial_pasos = []
    current_order = cw.current_state.sort_order
    all_states = cw.workflow.states.all().order_by('sort_order')
    
    history_logs = list(cw.history_logs.all())
    history_dates = { log.state_id: log.changed_at for log in sorted(history_logs, key=lambda x: x.changed_at) }

    for state in all_states:
        is_past = state.sort_order <= current_order
        historial_pasos.append({
            "nombre": state.name,
            "estado": "completado" if is_past else "pendiente",
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
                "description": item.comment or "Actualización de facturación.",
                "date": item.changed_at, 
                "color": color
            })
        else:
            is_inbound = item.direction == 'inbound'
            color = "#f59e0b" if is_inbound else "#8b5cf6" 
            status_text = "Constancia/Respuesta recibida" if is_inbound else "Factura enviada"
            
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
                "status": status_text,
                "description": f"Asunto: {item.subject or 'Sin asunto'}",
                "body": item.body if hasattr(item, 'body') else None,
                "date": item.created_at, 
                "color": color,
                "attachments": attachments_data # <-- PASAMOS LOS ADJUNTOS
            })

    # --- REDACTAR CORREO ---
    esperando_respuesta = cw.current_state.code in ['waiting_payment', 'esperando_abono'] 
    servicio = metadata.get("servicio_requerido", "los servicios prestados")
    asunto = f"Factura correspondiente a {servicio}"
    
    email_draft = {
        "to": contact_email,
        "subject": asunto,
        "body": "Estimados,\n\nAdjuntamos la factura correspondiente a nuestros servicios. Quedamos a la espera de la constancia de abono (voucher) respondiendo a este mismo correo o enviando el archivo adjunto.\n\nAtentamente,\nEl Equipo de Administración."
    }

    assigned_id = cw.assigned_to_id
    assigned_name = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email if cw.assigned_to else None

    return {
        "customer_id": cw.customer.id,
        "esperandoRespuesta": esperando_respuesta,
        "historialPasos": historial_pasos,
        "historyEvents": history_events,
        "emailDraft": email_draft,
        "assigned_to_id": assigned_id,
        "assigned_to_name": assigned_name,
        "current_user_id": request.user.id
    }
    
    
@router.post("/active/{cw_id}/mark-paid")
def mark_as_paid(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Marca la facturación como pagada y deriva automáticamente el cliente 
    al módulo de Soporte (Support).
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'billing')
    
    # 1. Obtenemos el flujo de facturación actual
    cw = get_object_or_404(
        CustomerWorkflow, 
        id=cw_id, 
        workflow__brand=tenant.brand,
        workflow__code='billing',
        finished_at__isnull=True 
    )

    if cw.assigned_to_id and cw.assigned_to_id != request.user.id:
        raise HttpError(403, "No puedes marcar este abono porque está asignado a otro ejecutivo.")

    # 2. Buscamos el estado final de Billing
    try:
        final_state = WorkflowState.objects.get(workflow=cw.workflow, code='paid')
    except WorkflowState.DoesNotExist:
        raise HttpError(400, "El estado final 'paid' no existe en el flujo de facturación.")

    # 3. Cerramos el flujo de Facturación
    cw.current_state = final_state
    cw.finished_at = timezone.now()
    cw.save()

    # Usamos tu modelo CustomerWorkflowHistory
    CustomerWorkflowHistory.objects.create(
        customer_workflow=cw,
        state=final_state,
        user=request.user, # Tu campo se llama 'user'
        comment="Constancia de abono verificada. Facturación completada."
    )

    # ==========================================
    # 4. Derivamos al módulo de Support
    # ==========================================
    try:
        support_workflow = Workflow.objects.get(brand=tenant.brand, code='support')
        # Obtenemos el primer estado basándonos en tu sort_order
        initial_support_state = support_workflow.states.order_by('sort_order').first()
    except Workflow.DoesNotExist:
        raise HttpError(400, "El flujo 'support' no está configurado para esta marca.")

    new_cw = CustomerWorkflow.objects.create(
        customer=cw.customer,
        workflow=support_workflow,
        current_state=initial_support_state,
        assigned_to=None, 
        metadata=cw.metadata 
    )

    CustomerWorkflowHistory.objects.create(
        customer_workflow=new_cw,
        state=initial_support_state,
        user=request.user,
        comment="Derivado automáticamente tras confirmación de abono."
    )

    return {
        "success": True, 
        "message": "Abono verificado exitosamente. El cliente ha sido derivado a Soporte."
    }
    

@router.get("/archived", response=List[BillingListRowOut])
def list_archived_trades(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de tratos finalizados (Ganados o Perdidos).
    Alimentará la vista de historial.
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'billing')
    
    # La diferencia clave: finished_at__isnull=False
    return CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='billing', 
        finished_at__isnull=False # <-- CRÍTICO: False porque ya terminaron
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-started_at')