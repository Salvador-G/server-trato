```python
from django.db import models
from django.conf import settings

# =========================
# WORKFLOW (El Proceso Padre - Aislado por marca)
# =========================
class Workflow(models.Model):
    brand = models.ForeignKey(
        "core.Brand", 
        on_delete=models.CASCADE, 
        related_name="workflows"
    )
    code = models.CharField(max_length=50, verbose_name="Código (Ej: trade, billing)")
    name = models.CharField(max_length=100, verbose_name="Nombre del Proceso")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Orden de visualización")
    
    # CONFIGURACIÓN DE BANDEJA DE CORREO (BYOE)
    email_config = models.ForeignKey(
        "communications.EmailConfiguration",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_workflows",
        help_text="Bandeja de correo usada para enviar/recibir en este proceso"
    )
    
    is_active = models.BooleanField(default=True)
    
    permissions = models.ManyToManyField(
        "core.Permission", 
        blank=True, 
        related_name="workflows",
        verbose_name="Permisos requeridos"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Workflow"
        verbose_name_plural = "Workflows"
        ordering = ["sort_order"]
        unique_together = ("brand", "code")

    def __str__(self):
        return f"{self.name} ({self.brand.name})"

# =========================
# WORKFLOW STATE (Los pasos del proceso)
# =========================
class WorkflowState(models.Model):
    workflow = models.ForeignKey(
        Workflow, 
        on_delete=models.CASCADE, 
        related_name="states",
        verbose_name="Proceso"
    )
    code = models.CharField(max_length=50, verbose_name="Código (Ej: pending, approved)")
    name = models.CharField(max_length=100, verbose_name="Nombre del Estado")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="Orden cronológico")
    is_final = models.BooleanField(
        default=False, 
        help_text="Marcar si este estado finaliza el proceso (Ej: Completado, Rechazado)"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Workflow State"
        verbose_name_plural = "Workflow States"
        ordering = ["workflow", "sort_order"]
        unique_together = ("workflow", "code")

    def __str__(self):
        return f"{self.workflow.name} - {self.name}"

# =========================
# CUSTOMER WORKFLOW (El proceso activo del cliente)
# =========================
class CustomerWorkflow(models.Model):
    customer = models.ForeignKey(
        "customers.Customer", 
        on_delete=models.CASCADE, 
        related_name="active_workflows",
        verbose_name="Cliente"
    )
    workflow = models.ForeignKey(
        Workflow, 
        on_delete=models.PROTECT, 
        related_name="customer_instances",
        verbose_name="Proceso"
    )
    current_state = models.ForeignKey(
        WorkflowState, 
        on_delete=models.RESTRICT, 
        related_name="current_customers",
        verbose_name="Estado Actual"
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name="assigned_workflows",
        verbose_name="Asignado a"
    )

    # ---> NUEVO CAMPO: La Pizarra de Negociación <---
    metadata = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Datos Comerciales Vivos",
        help_text="Contexto actual del flujo (ej. plan negociado, montos, credenciales)"
    )

    started_at = models.DateTimeField(auto_now_add=True, verbose_name="Iniciado el")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="Finalizado el")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Customer Workflow"
        verbose_name_plural = "Customer Workflows"
        constraints = [
            models.UniqueConstraint(
                fields=['customer', 'workflow', 'finished_at'], 
                name='unique_active_workflow_per_customer'
            )
        ]

    def __str__(self):
        return f"{self.customer} | {self.workflow.name} ({self.current_state.name})"

# =========================
# CUSTOMER WORKFLOW HISTORY (La bitácora inmutable)
# =========================
class CustomerWorkflowHistory(models.Model):
    customer_workflow = models.ForeignKey(
        CustomerWorkflow, 
        on_delete=models.CASCADE, 
        related_name="history_logs",
        verbose_name="Proceso del Cliente"
    )
    state = models.ForeignKey(
        WorkflowState, 
        on_delete=models.RESTRICT, 
        verbose_name="Estado Registrado"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        verbose_name="Usuario responsable"
    )
    comment = models.TextField(blank=True, verbose_name="Comentario / Motivo")
    changed_at = models.DateTimeField(auto_now_add=True, verbose_name="Fecha de cambio")

    class Meta:
        verbose_name = "Workflow History Log"
        verbose_name_plural = "Workflow History Logs"
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.customer_workflow.id} -> {self.state.name}"


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
        
    return 200, {"success": True, "message": "Te has asignado este cliente exitosamente."}



# workflows/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from core.models import Brand
from .models import Workflow, WorkflowState

# Definimos la plantilla maestra de tus flujos fijos
DEFAULT_WORKFLOWS = [
    {
        "code": "trade",
        "name": "Comercial / Ventas",
        "sort_order": 10,
        "states": [
            {"code": "lead", "name": "Prospecto", "sort_order": 1, "is_final": False},
            {"code": "negotiation", "name": "Negociación", "sort_order": 2, "is_final": False},
            {"code": "won", "name": "Ganado", "sort_order": 3, "is_final": True},
            {"code": "lost", "name": "Perdido", "sort_order": 4, "is_final": True},
        ]
    },
    {
        "code": "contract",
        "name": "Legal / Contratos",
        "sort_order": 20,
        "states": [
            {"code": "draft", "name": "Borrador Generado", "sort_order": 1, "is_final": False},
            {"code": "review", "name": "En Revisión Cliente", "sort_order": 2, "is_final": False},
            {"code": "signed", "name": "Contrato Firmado", "sort_order": 3, "is_final": True},
        ]
    },
    {
        "code": "billing",
        "name": "Facturación",
        "sort_order": 30,
        "states": [
            {"code": "pending", "name": "Pendiente de Pago", "sort_order": 1, "is_final": False},
            {"code": "paid", "name": "Pagado", "sort_order": 2, "is_final": True},
        ]
    },
    {
        "code": "support",
        "name": "Soporte / Onboarding",
        "sort_order": 40,
        "states": [
            {"code": "open", "name": "Ticket Abierto", "sort_order": 1, "is_final": False},
            {"code": "in_progress", "name": "En Progreso", "sort_order": 2, "is_final": False},
            {"code": "resolved", "name": "Resuelto / Entregado", "sort_order": 3, "is_final": True},
        ]
    }
]

@receiver(post_save, sender=Brand)
def create_default_workflows_for_new_brand(sender, instance, created, **kwargs):
    """
    Se ejecuta automáticamente cada vez que se guarda un Brand.
    Si el Brand es NUEVO (created = True), le generamos sus plantillas de procesos.
    """
    if created:
        # Usamos transaction.atomic para que si algo falla, no se creen procesos a medias
        with transaction.atomic():
            for wf_data in DEFAULT_WORKFLOWS:
                # 1. Creamos el proceso padre
                workflow = Workflow.objects.create(
                    brand=instance,
                    code=wf_data["code"],
                    name=wf_data["name"],
                    sort_order=wf_data["sort_order"]
                )
                
                # 2. Creamos los estados (columnas) para ese proceso
                for state_data in wf_data["states"]:
                    WorkflowState.objects.create(
                        workflow=workflow,
                        code=state_data["code"],
                        name=state_data["name"],
                        sort_order=state_data["sort_order"],
                        is_final=state_data["is_final"]
                    )
```