# workflows/schemas.py
from ninja import ModelSchema, Schema
from typing import List, Optional, Dict, Any

from .models import Workflow, WorkflowState, CustomerWorkflow, CustomerWorkflowHistory

# ==========================================
# 1. CONFIGURACIÓN (Lectura y Edición)
# ==========================================

class WorkflowStateOut(ModelSchema):
    class Meta:
        model = WorkflowState
        fields = ['id', 'code', 'name', 'sort_order', 'is_final']

class WorkflowOut(ModelSchema):
    states: List[WorkflowStateOut] 
    email_config_id: Optional[int] # <-- Exponemos la clave foránea
    
    class Meta:
        model = Workflow
        fields = ['id', 'code', 'name', 'sort_order', 'is_active']

class WorkflowUpdate(Schema):
    """El cliente puede asignar una bandeja de correo específica o desactivar el módulo"""
    email_config_id: Optional[int] = None # <-- Permite actualizar la asignación
    is_active: Optional[bool] = None

# ==========================================
# 2. OPERACIÓN (El día a día del equipo)
# ==========================================

class WorkflowHistoryOut(ModelSchema):
    state_name: str = None
    user_email: str = None
    
    class Meta:
        model = CustomerWorkflowHistory
        fields = ['id', 'comment', 'changed_at']
        
    @staticmethod
    def resolve_state_name(obj: CustomerWorkflowHistory) -> str:
        return obj.state.name
        
    @staticmethod
    def resolve_user_email(obj: CustomerWorkflowHistory) -> str:
        return obj.user.email if obj.user else "Sistema"

class CustomerWorkflowOut(ModelSchema):
    customer_id: int
    workflow_id: int
    current_state_id: int
    
    customer_name: str = None
    workflow_code: str = None 
    current_state_code: str = None 
    assigned_to_email: Optional[str] = None
    
    # ---> NUEVO: Exponemos la metadata al frontend <---
    metadata: Dict[str, Any] 
    
    class Meta:
        model = CustomerWorkflow
        # Añadido 'metadata' a los fields
        fields = ['id', 'started_at', 'finished_at', 'metadata']

    @staticmethod
    def resolve_customer_name(obj: CustomerWorkflow) -> str:
        return str(obj.customer)
        
    @staticmethod
    def resolve_workflow_code(obj: CustomerWorkflow) -> str:
        return obj.workflow.code
        
    @staticmethod
    def resolve_current_state_code(obj: CustomerWorkflow) -> str:
        return obj.current_state.code
        
    @staticmethod
    def resolve_assigned_to_email(obj: CustomerWorkflow) -> Optional[str]:
        return obj.assigned_to.email if obj.assigned_to else None

# ==========================================
# 3. PAYLOADS DE ENTRADA (Mover al cliente)
# ==========================================

class CustomerWorkflowCreate(Schema):
    """Payload para ingresar a un cliente al flujo de 'Trade' (u otro)"""
    customer_id: int
    workflow_code: str 
    assigned_to_id: Optional[int] = None
    initial_comment: Optional[str] = "Proceso iniciado automáticamente."
    
    # ---> NUEVO: Permite inyectar datos iniciales desde el formulario <---
    metadata: Optional[Dict[str, Any]] = {}

class WorkflowTransition(Schema):
    """Payload para avanzar al cliente al siguiente estado"""
    new_state_code: str 
    comment: Optional[str] = None
    
    # ---> NUEVO: Permite actualizar (merge) los datos comerciales al cambiar de estado <---
    metadata_update: Optional[Dict[str, Any]] = None