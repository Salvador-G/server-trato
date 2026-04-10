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
from core.dependencies import get_current_tenant

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
        
    return cw

@router.get("/{cw_id}/history", response=List[WorkflowHistoryOut])
def get_workflow_history(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Obtiene el historial de movimientos de un proceso (Auditoría)"""
    tenant = get_current_tenant(request, x_brand_id)
    cw = get_object_or_404(CustomerWorkflow, id=cw_id, workflow__brand=tenant.brand)
    
    return cw.history_logs.select_related('state', 'user').order_by('-changed_at')