# modules_api/routers/contract.py
from ninja import Router, Header
from ninja_jwt.authentication import JWTAuth
from typing import List

from django.shortcuts import get_object_or_404
from itertools import chain
from communications.models import Message
from workflows.models import CustomerWorkflow
from core.dependencies import get_current_tenant
from ..schemas import ContractListRowOut, TradeMainOut

router = Router(tags=["Modules API - Contract (Operaciones/Legal)"], auth=JWTAuth())

@router.get("/active", response=List[ContractListRowOut])
def list_active_contracts(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de contratos en curso (no finalizados).
    Alimentará la vista de ContractList.vue
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    # Filtramos: Marca actual, flujo de 'contract', y que no estén finalizados
    cws = CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='contract', 
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
        
        # Lógica de fallback para B2B vs B2C
        ruc = empresa.tax_id if empresa else "N/A"
        razon_social = empresa.legal_name if empresa else (cliente.contact.full_name if cliente.contact else "Sin Nombre")
        
        # Personal asignado (Heredado de Ventas al momento de derivar)
        if cw.assigned_to:
            personal = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email
        else:
            personal = "Sin asignar"

        resultados.append({
            "id": cw.id,
            "fecha": cw.started_at, # Pasamos el objeto datetime crudo, el frontend lo formatea
            "ruc": ruc,
            "razonSocial": razon_social,
            "personal": personal,
            "estadoId": cw.current_state.code 
        })

    return resultados

@router.get("/active/{cw_id}/main", response=TradeMainOut)
def get_contract_main_data(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    # Validamos que sea un contrato y pertenezca a la marca
    cw = get_object_or_404(
        CustomerWorkflow.objects.select_related(
            'workflow', 'current_state', 'customer__contact'
        ), 
        id=cw_id, 
        workflow__brand=tenant.brand,
        workflow__code='contract' # <-- IMPORTANTE
    )

    metadata = cw.metadata or {}
    contact_email = cw.customer.contact.email if cw.customer.contact else ""
    
    # --- PIPELINE DE PASOS (Stepper) ---
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

    # --- HISTORIAL OMNICANAL (Workflow Logs + Emails) ---
    history_events = []
    messages = Message.objects.filter(conversation__customer_workflow=cw).select_related('conversation')

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
            history_events.append({
                "status": status_text,
                "description": f"Asunto: {item.subject or 'Sin asunto'}",
                "body": item.body if hasattr(item, 'body') else None,
                "date": item.created_at, 
                "color": color
            })

    # --- REDACTAR CORREO (Draft Inicial) ---
    esperando_respuesta = cw.current_state.code == 'review' # Solo espera respuesta si está en revisión de cliente
    servicio = metadata.get("servicio_requerido", "")
    asunto = f"Contrato de Servicio - {servicio}" if servicio else "Documentación Legal"
    
    email_draft = {
        "to": contact_email,
        "subject": asunto,
        "body": "Estimados,\n\nAdjunto enviamos el borrador del contrato para su revisión y conformidad..."
    }

    assigned_id = cw.assigned_to_id
    assigned_name = None
    if cw.assigned_to:
        assigned_name = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email

    return {
        "esperandoRespuesta": esperando_respuesta,
        "historialPasos": historial_pasos,
        "historyEvents": history_events,
        "emailDraft": email_draft,
        "assigned_to_id": assigned_id,
        "assigned_to_name": assigned_name,
        "current_user_id": request.user.id
    }