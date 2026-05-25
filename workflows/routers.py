# workflows/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.utils import timezone
from ninja_jwt.authentication import JWTAuth

from .models import Workflow, WorkflowState, CustomerWorkflow, CustomerWorkflowHistory
from communications.models import EmailConfiguration
from customers.models import Customer
from .schemas import (
    WorkflowOut, WorkflowUpdate,
    CustomerWorkflowOut, CustomerWorkflowCreate, 
    WorkflowTransition, WorkflowHistoryOut
)
from core.utils.audit import log_audit_event
from core.dependencies import get_current_tenant, verify_module_access

router = Router(tags=["Workflows (Procesos)"], auth=JWTAuth())

# ==========================================
# 1. CONFIGURACIÓN (Lectura y Edición de Plantillas)
# ==========================================

@router.get("/templates", response=List[WorkflowOut])
def list_workflows(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Lista los flujos disponibles (trade, contract, billing, support) y sus estados"""
    tenant = get_current_tenant(request, x_brand_id)
    return Workflow.objects.filter(brand=tenant.brand).prefetch_related('states')

@router.patch("/templates/{workflow_code}", response=WorkflowOut)
def update_workflow_settings(request, workflow_code: str, payload: WorkflowUpdate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Permite al dueño asignar una bandeja de correo al flujo y/o activarlo/desactivarlo"""
    tenant = get_current_tenant(request, x_brand_id)
    workflow = get_object_or_404(Workflow, code=workflow_code, brand=tenant.brand)
    
    update_data = payload.dict(exclude_unset=True)
    
    if 'email_config_id' in update_data and update_data['email_config_id'] is not None:
        config_id = update_data['email_config_id']
        email_config = get_object_or_404(EmailConfiguration, id=config_id, brand=tenant.brand)
        workflow.email_config = email_config
        del update_data['email_config_id']
    elif 'email_config_id' in update_data and update_data['email_config_id'] is None:
        workflow.email_config = None
        del update_data['email_config_id']

    if update_data:
        for attr, value in update_data.items():
            setattr(workflow, attr, value)
            
    workflow.save()
        
    return workflow


# ==========================================
# 2. OPERACIÓN (Iniciar y Mover Clientes)
# ==========================================

@router.get("/active", response=List[CustomerWorkflowOut])
def list_active_workflows(request, workflow_code: str = None, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Lista los procesos activos. 
    Ej: /api/workflows/active?workflow_code=trade -> Para el dashboard de Ventas
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    qs = CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        finished_at__isnull=True
    ).select_related('customer', 'workflow', 'current_state', 'assigned_to')
    
    if workflow_code:
        qs = qs.filter(workflow__code=workflow_code)
        
    return qs

@router.post("/start", response={201: CustomerWorkflowOut})
def start_workflow(request, payload: CustomerWorkflowCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Inicia un nuevo proceso para un cliente (Entra al Estado 1)"""
    tenant = get_current_tenant(request, x_brand_id)
    
    customer = get_object_or_404(Customer, id=payload.customer_id, brand=tenant.brand)
    workflow = get_object_or_404(Workflow, code=payload.workflow_code, brand=tenant.brand)
    
    if CustomerWorkflow.objects.filter(customer=customer, workflow=workflow, finished_at__isnull=True).exists():
        raise HttpError(400, f"El cliente ya tiene un proceso de '{workflow.name}' activo.")

    initial_state = workflow.states.order_by('sort_order').first()
    if not initial_state:
        raise HttpError(500, "Este workflow no tiene estados configurados.")

    with transaction.atomic():
        cw = CustomerWorkflow.objects.create(
            customer=customer,
            workflow=workflow,
            current_state=initial_state,
            assigned_to_id=payload.assigned_to_id,
            metadata=payload.metadata or {} # <-- NUEVO: Guardamos la data inicial
        )
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=cw,
            state=initial_state,
            user=request.user,
            comment=payload.initial_comment
        )
        
    return 201, cw

@router.post("/{cw_id}/transition", response=CustomerWorkflowOut)
def transition_workflow(request, cw_id: int, payload: WorkflowTransition, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Mueve al cliente a un nuevo estado (Columna del Kanban)"""
    tenant = get_current_tenant(request, x_brand_id)
    
    cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand)
    
    if cw.finished_at:
        raise HttpError(400, "No puedes mover un proceso que ya está finalizado.")

    new_state = get_object_or_404(WorkflowState, code=payload.new_state_code, workflow=cw.workflow)
    
    with transaction.atomic():
        old_state_name= cw.current_state.name
        cw.current_state = new_state
        
        # <-- NUEVO: Lógica de actualización de Metadata (Merge parcial) -->
        if payload.metadata_update:
            # Aseguramos que la metadata actual sea un diccionario
            current_metadata = cw.metadata if isinstance(cw.metadata, dict) else {}
            # Actualizamos las llaves existentes o agregamos nuevas sin borrar el resto
            current_metadata.update(payload.metadata_update)
            cw.metadata = current_metadata
        
        if new_state.is_final:
            cw.finished_at = timezone.now()
            
        cw.save()
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=cw,
            state=new_state,
            user=request.user,
            comment=payload.comment or f"Movido a {new_state.name}"
        )
        
        # Auditoría general
        cliente_nombre = cw.customer.company.legal_name if cw.customer.company else "Cliente B2C"
        log_audit_event(
            request=request,
            action=f"{cw.workflow.code.upper()}_STATE_CHANGED", # Ej: TRADE_STATE_CHANGED
            actor=request.user,
            brand=tenant.brand,
            details={
                "cw_id": cw.id,
                "customer_name": cliente_nombre,
                "old_state": old_state_name,
                "new_state": new_state.name,
                "comment": payload.comment
            }
        )
        
    return cw

@router.get("/{cw_id}/history", response=List[WorkflowHistoryOut])
def get_workflow_history(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Obtiene el historial de movimientos de un proceso (Auditoría)"""
    tenant = get_current_tenant(request, x_brand_id)
    cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand)
    
    return cw.history_logs.select_related('state', 'user').order_by('-changed_at')

@router.post("/{cw_id}/derive-to-contract", response={200: CustomerWorkflowOut})
def derive_to_contract(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    trade_cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand, workflow__code='trade')
    
    if trade_cw.finished_at:
        raise HttpError(400, "Este proceso ya está finalizado y no puede derivarse.")

    # === NUEVO: VALIDACIÓN DE PROPIEDAD ===
    if trade_cw.assigned_to and trade_cw.assigned_to != request.user:
        dueño = f"{trade_cw.assigned_to.first_name} {trade_cw.assigned_to.last_name}".strip() or trade_cw.assigned_to.email
        raise HttpError(403, f"Acceso denegado. Este lead está siendo atendido por {dueño}.")

    estado_ganado = get_object_or_404(WorkflowState, code='won', workflow=trade_cw.workflow)
    workflow_contract = get_object_or_404(Workflow, code='contract', brand=tenant.brand)
    estado_inicial_contract = workflow_contract.states.order_by('sort_order').first()

    with transaction.atomic():
        # Auto-asignar si era un lead huérfano de la web
        if trade_cw.assigned_to is None:
            trade_cw.assigned_to = request.user
            
        # --- A. CERRAR EL TRADE ---
        trade_cw.current_state = estado_ganado
        trade_cw.finished_at = timezone.now()
        trade_cw.save()
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=trade_cw,
            state=estado_ganado,
            user=request.user,
            comment="Negocio ganado. Derivado a Operaciones/Legal."
        )

        # --- B. CREAR EL NUEVO CONTRATO ---
        # Rescatamos la metadata actual y le añadimos la referencia de origen
        metadata_traspaso = trade_cw.metadata if isinstance(trade_cw.metadata, dict) else {}
        metadata_traspaso['origen_trade_id'] = trade_cw.id

        nuevo_contract = CustomerWorkflow.objects.create(
            customer=trade_cw.customer,
            workflow=workflow_contract,
            current_state=estado_inicial_contract,
            assigned_to_id=trade_cw.assigned_to_id, # Hereda el mismo responsable inicial
            metadata=metadata_traspaso
        )
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=nuevo_contract,
            state=estado_inicial_contract,
            user=request.user,
            comment="Proceso iniciado desde derivación de Trade."
        )

        # Auditoría general del traspaso
        cliente_nombre = trade_cw.customer.company.legal_name if trade_cw.customer.company else "Cliente B2C"
        log_audit_event(
            request=request,
            action='CONTRACT_GENERATED',
            actor=request.user,
            brand=tenant.brand,
            details={
                "trade_cw_id": trade_cw.id,
                "contract_cw_id": nuevo_contract.id,
                "customer_name": cliente_nombre
            }
        )
        
    # Devolvemos el nuevo contrato para que el Front pueda redirigir
    return 200, nuevo_contract

@router.post("/{cw_id}/decline", response={200: dict})
def decline_trade(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    trade_cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand, workflow__code='trade')
    
    if trade_cw.finished_at:
        raise HttpError(400, "Este proceso ya está finalizado.")

    # === NUEVO: VALIDACIÓN DE PROPIEDAD ===
    if trade_cw.assigned_to and trade_cw.assigned_to != request.user:
        dueño = f"{trade_cw.assigned_to.first_name} {trade_cw.assigned_to.last_name}".strip() or trade_cw.assigned_to.email
        raise HttpError(403, f"Acceso denegado. Este lead está siendo atendido por {dueño}.")

    estado_perdido = get_object_or_404(WorkflowState, code='lost', workflow=trade_cw.workflow)

    with transaction.atomic():
        # Auto-asignar si era un lead huérfano de la web
        if trade_cw.assigned_to is None:
            trade_cw.assigned_to = request.user
            
        trade_cw.current_state = estado_perdido
        trade_cw.finished_at = timezone.now()
        trade_cw.save()
        
        CustomerWorkflowHistory.objects.create(
            customer_workflow=trade_cw,
            state=estado_perdido,
            user=request.user,
            comment="El negocio fue marcado como perdido por el usuario."
        )
        
        # Auditoría general del marcado como perdido
        cliente_nombre = trade_cw.customer.company.legal_name if trade_cw.customer.company else "Cliente B2C"
        log_audit_event(
            request=request,
            action='TRADE_STATE_CHANGED',
            actor=request.user,
            brand=tenant.brand,
            details={
                "cw_id": trade_cw.id,
                "customer_name": cliente_nombre,
                "new_state": "Perdido",
                "reason": "Declinado manualmente por el asesor"
            }
        )

    return 200, {"success": True, "message": "Proceso marcado como perdido."}

@router.post("/{cw_id}/reassign", response={200: dict})
def reassign_workflow(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Permite a un usuario tomar el control de un proceso (reasignárselo a sí mismo),
    útil cuando el asesor original está ausente o deshabilitado.
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    
    
    with transaction.atomic():
        try:
            cw = CustomerWorkflow.objects.select_for_update().get(
                id=cw_id, 
                workflow__brand=tenant.brand
            )
        except CustomerWorkflow.DoesNotExist:
            raise HttpError(404, "Proceso no encontrado")
            
        verify_module_access(tenant, cw.workflow.code)
        
        if cw.finished_at:
            raise HttpError(400, "No puedes reasignar un proceso que ya está finalizado.")
            
        # Evitar reasignarse algo que ya es tuyo
        if cw.assigned_to == request.user:
            return 200, {"success": True, "message": "Este lead ya está asignado a ti."}
            
        dueño_anterior = "Nadie (Huérfano)"
        if cw.assigned_to:
            dueño_anterior = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email
            
        # Efectuar el cambio
        cw.assigned_to = request.user
        cw.save()
        
        # Registrar en la auditoría
        CustomerWorkflowHistory.objects.create(
            customer_workflow=cw,
            state=cw.current_state,
            user=request.user,
            comment=f"Lead reasignado manualmente. Dueño anterior: {dueño_anterior}."
        )
        
        # Auditoría general del cambio de asignación
        cliente_nombre = cw.customer.company.legal_name if cw.customer.company else "Cliente B2C"
        log_audit_event(
            request=request,
            action=f"{cw.workflow.code.upper()}_TAKEN", # Ej: TRADE_TAKEN
            actor=request.user,
            brand=tenant.brand,
            details={
                "cw_id": cw.id,
                "workflow_type": cw.workflow.code,
                "customer_name": cliente_nombre,
                "previous_owner": dueño_anterior
            }
        )
        
    return 200, {"success": True, "message": "Te has asignado este cliente exitosamente."}