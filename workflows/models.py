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