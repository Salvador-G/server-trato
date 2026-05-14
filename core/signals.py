# core/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from .models import Brand, Role

DEFAULT_ROLES = [
    ("Manager", "Gestor general con acceso de lectura/escritura a todos los módulos operativos y administrativos."),
    ("Trade", "Especialista en Ventas, Prospección y CRM."),
    ("Contract", "Gestor Legal, revisión y aprobación de Contratos."),
    ("Billing", "Encargado de Facturación, Cobranzas y control de pagos."),
    ("Support", "Atención al Cliente, Onboarding y resolución de tickets."),
]

@receiver(post_save, sender=Brand)
def setup_brand_roles(sender, instance, created, **kwargs):
    """
    Inicializa la jerarquía operativa (Roles) cuando se crea una nueva Marca.
    """
    if created:
        with transaction.atomic():
            for role_name, description in DEFAULT_ROLES:
                Role.objects.get_or_create(
                    brand=instance,
                    name=role_name,
                    defaults={"description": description}
                )