# documents/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction

from core.models import Brand
from .models import DocumentType

# Definimos los tipos de documentos estándar para cada módulo
DEFAULT_DOCUMENT_TYPES = [
    {"code": "quote", "name": "Cotización Comercial"},        # Para Trade
    {"code": "contract", "name": "Contrato Legal"},           # Para Contract
    {"code": "invoice", "name": "Factura / Boleta"},          # Para Billing
    {"code": "support_file", "name": "Adjunto de Soporte"},   # Para Support
    {"code": "other", "name": "Otros Documentos"},            # Fallback general
]

@receiver(post_save, sender=Brand)
def create_default_document_types(sender, instance, created, **kwargs):
    """
    Se ejecuta automáticamente al crear un nuevo Brand (Empresa).
    Genera el catálogo base de tipos de documentos.
    """
    if created:
        with transaction.atomic():
            for doc_data in DEFAULT_DOCUMENT_TYPES:
                DocumentType.objects.create(
                    brand=instance,
                    code=doc_data["code"],
                    name=doc_data["name"]
                )