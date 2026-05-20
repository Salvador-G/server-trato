# core/signals.py
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.db import transaction

from .models import Brand, Role, Permission

# 1. PERMISOS MAESTROS
SYSTEM_PERMISSIONS = {
    # Trade
    "trade.view": "Permite ver la lista de prospectos y el pipeline comercial.",
    "trade.create": "Permite registrar nuevos prospectos (Leads).",
    "trade.edit": "Permite actualizar la información de los prospectos en curso.",
    "trade.reassign": "Permite reasignarse o cambiar el dueño de un lead comercial.",
    # Contract
    "contract.view": "Permite acceder a la lista de contratos y expedientes activos.",
    "contract.write": "Permite redactar correos formales y cargar borradores de contratos.",
    "contract.sign": "Permite validar y marcar un contrato como firmado.",
    "contract.reassign": "Permite tomar el control de un expediente asignado a otro legal.",
    # Billing
    "billing.view": "Permite visualizar el estado de cuenta y las órdenes de pago.",
    "billing.write": "Permite generar comprobantes o editar montos de facturación.",
    "billing.mark_paid": "Permite registrar pagos manuales o conciliar transacciones.",
    # Support
    "support.view": "Permite ver la cola de tickets de soporte y onboarding.",
    "support.manage": "Permite responder mensajes y adjuntar documentación en un ticket.",
    "support.resolve": "Permite marcar un ticket de soporte como cerrado.",
    # Admin
    "admin.view_users": "Permite ver la lista de trabajadores asignados a la marca.",
    "admin.invite_user": "Permite enviar invitaciones por correo para sumar personal.",
    "admin.manage_brand": "Permite alterar configuraciones críticas de marca."
}

# 2. PLANTILLAS DE ROLES (Ahora con descripción Y permisos)
ROLE_TEMPLATES = {
    "Owner": {
        "description": "Administrador principal y dueño de la cuenta SaaS.",
        "permissions": list(SYSTEM_PERMISSIONS.keys()) # Acceso total
    },
    "Manager": {
        "description": "Gestor general con acceso de lectura/escritura a todos los módulos operativos y administrativos.",
        "permissions": list(SYSTEM_PERMISSIONS.keys()) # Acceso total
    },
    "Trade": {
        "description": "Especialista en Ventas, Prospección y CRM.",
        "permissions": ["trade.view", "trade.create", "trade.edit", "trade.reassign"]
    },
    "Contract": {
        "description": "Gestor Legal, revisión y aprobación de Contratos.",
        "permissions": ["contract.view", "contract.write", "contract.sign", "contract.reassign"]
    },
    "Billing": {
        "description": "Encargado de Facturación, Cobranzas y control de pagos.",
        "permissions": ["billing.view", "billing.write", "billing.mark_paid"]
    },
    "Support": {
        "description": "Atención al Cliente, Onboarding y resolución de tickets.",
        "permissions": ["support.view", "support.manage", "support.resolve"]
    }
}


@receiver(post_migrate)
def seed_system_permissions(sender, **kwargs):
    """
    Se ejecuta automáticamente tras correr las migraciones.
    Mantiene sincronizada la tabla de permisos en la BD con tu código.
    """
    if sender.name == 'core':
        print("Sincronizando permisos maestros del sistema SaaS...")
        for code, description in SYSTEM_PERMISSIONS.items():
            Permission.objects.get_or_create(
                code=code,
                defaults={"description": description}
            )


@receiver(post_save, sender=Brand)
def setup_brand_roles(sender, instance, created, **kwargs):
    """
    Inicializa la jerarquía operativa (Roles) cuando se crea una nueva Marca,
    agregando las descripciones correctas y vinculando sus permisos estandarizados.
    """
    if created:
        with transaction.atomic():
            for role_name, data in ROLE_TEMPLATES.items():
                
                # 1. Creamos el Rol con tu descripción personalizada
                role, _ = Role.objects.get_or_create(
                    brand=instance,
                    name=role_name,
                    defaults={"description": data["description"]}
                )
                
                # 2. Buscamos los permisos reales en la BD y los asociamos (M2M)
                db_permissions = Permission.objects.filter(code__in=data["permissions"])
                role.permissions.set(db_permissions)