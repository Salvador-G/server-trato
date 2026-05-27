# modules_api/routers/contract.py
import os
from ninja import Router, Header
from ninja.pagination import paginate, LimitOffsetPagination
from ninja_jwt.authentication import JWTAuth
from typing import List
from django.utils import timezone
from ninja.errors import HttpError
from django.shortcuts import get_object_or_404
from itertools import chain
from communications.models import Message
from workflows.models import Workflow, WorkflowState, CustomerWorkflow, CustomerWorkflowHistory 
from core.dependencies import get_current_tenant, verify_module_access
from core.utils.audit import log_audit_event
from ..schemas import ContractListRowOut, TradeMainOut

router = Router(tags=["Modules API - Contract (Operaciones/Legal)"], auth=JWTAuth())

@router.get("/active", response=List[ContractListRowOut])
@paginate(LimitOffsetPagination)
def list_active_contracts(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de contratos en curso (no finalizados).
    Alimentará la vista de ContractList.vue
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'contract')
    
    # Filtramos: Marca actual, flujo de 'contract', y que no estén finalizados
    # Ninja aplicará LIMIT/OFFSET y los resolvers del Schema harán el formateo
    return CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='contract', 
        finished_at__isnull=True
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-started_at')

@router.get("/active/{cw_id}/main", response=TradeMainOut)
def get_contract_main_data(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'contract')
    
    cw = get_object_or_404(
        CustomerWorkflow.objects.select_related(
            'workflow', 'current_state', 'customer__contact'
        ), 
        id=cw_id, 
        workflow__brand=tenant.brand,
        workflow__code='contract'
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
    # AÑADIDO: prefetch_related para los adjuntos
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
                "description": item.comment or "Actualización de contrato.",
                "date": item.changed_at, 
                "color": color
            })
        else:
            is_inbound = item.direction == 'inbound'
            color = "#f59e0b" if is_inbound else "#3b82f6"
            status_text = "Cliente respondió" if is_inbound else "Correo enviado"
            
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
    esperando_respuesta = cw.current_state.code == 'review'
    servicio = metadata.get("servicio_requerido", "")
    asunto = f"Contrato de Servicio - {servicio}" if servicio else "Documentación Legal"
    
    email_draft = {
        "to": contact_email,
        "subject": asunto,
        "body": "Estimados,\n\nAdjunto enviamos el borrador del contrato para su revisión y conformidad..."
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
    
@router.post("/active/{cw_id}/mark-signed")
def mark_as_signed(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Marca el contrato como firmado y deriva automáticamente el cliente 
    al módulo de Facturación (Billing).
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    verify_module_access(tenant, 'contract')
    
    cw = get_object_or_404(
        CustomerWorkflow, 
        id=cw_id, 
        workflow__brand=tenant.brand,
        workflow__code='contract',
        finished_at__isnull=True
    )

    if cw.assigned_to_id and cw.assigned_to_id != request.user.id:
        raise HttpError(403, "No puedes marcar este contrato porque está asignado a otro legal.")

    try:
        final_state = WorkflowState.objects.get(workflow=cw.workflow, code='signed')
    except WorkflowState.DoesNotExist:
        raise HttpError(400, "El estado final 'signed' no existe en el flujo legal.")

    cw.current_state = final_state
    cw.finished_at = timezone.now()
    cw.save()

    CustomerWorkflowHistory.objects.create(
        customer_workflow=cw,
        state=final_state,
        user=request.user,
        comment="Contrato firmado validado. Fase legal completada."
    )

    # Derivamos a Billing
    try:
        billing_workflow = Workflow.objects.get(brand=tenant.brand, code='billing')
        initial_billing_state = billing_workflow.states.order_by('sort_order').first()
    except Workflow.DoesNotExist:
        raise HttpError(400, "El flujo 'billing' no está configurado para esta marca.")

    new_cw = CustomerWorkflow.objects.create(
        customer=cw.customer,
        workflow=billing_workflow,
        current_state=initial_billing_state,
        assigned_to=None, 
        metadata=cw.metadata 
    )

    CustomerWorkflowHistory.objects.create(
        customer_workflow=new_cw,
        state=initial_billing_state,
        user=request.user,
        comment="Derivado automáticamente tras firma de contrato."
    )
    
    cliente_nombre = cw.customer.company.legal_name if cw.customer.company else "Cliente B2C"
    log_audit_event(
        request=request,
        action='CONTRACT_SIGNED',
        actor=request.user,
        brand=tenant.brand,
        details={
            "cw_id": cw.id,
            "customer_name": cliente_nombre,
            "next_step": "billing_created",
            "new_cw_id": new_cw.id
        }
    )

    return {
        "success": True, 
        "message": "Contrato firmado registrado. El cliente ha sido derivado a Facturación."
    }
    

@router.get("/archived", response=List[ContractListRowOut])
def list_archived_contracts(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de contratos finalizados.
    Alimentará la vista de historial.
    """
    tenant = get_current_tenant(request, x_brand_id)
    verify_module_access(tenant, 'contract')
    
    # La diferencia clave: finished_at__isnull=False
    return CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='contract', 
        finished_at__isnull=False # <-- CRÍTICO: False porque ya terminaron
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-started_at')