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
            {"code": "declined", "name": "Contrato Rechazado", "sort_order": 4, "is_final": True},
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