# documents/routers.py
from ninja import Router, Header, File, Form
from ninja.files import UploadedFile
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.db import transaction
from ninja_jwt.authentication import JWTAuth
from django.core.exceptions import ValidationError
from .models import Document, DocumentType
from .schemas import DocumentOut, DocumentTypeOut, DocumentUploadPayload
from core.dependencies import get_current_tenant
from customers.models import Customer

router = Router(tags=["Documents (Archivos)"], auth=JWTAuth())

@router.get("/types", response=List[DocumentTypeOut])
def list_document_types(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Devuelve los tipos de documentos disponibles (Contrato, Factura, etc.)"""
    tenant = get_current_tenant(request, x_brand_id)
    return DocumentType.objects.filter(brand=tenant.brand)

@router.get("/customer/{customer_id}", response=List[DocumentOut])
def list_customer_documents(request, customer_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Obtiene todos los documentos subidos para un cliente específico."""
    tenant = get_current_tenant(request, x_brand_id)
    return Document.objects.filter(
        brand=tenant.brand, 
        customer_id=customer_id
    ).select_related('document_type', 'created_by')

@router.post("/upload", response={201: DocumentOut})
def upload_document(
    request,
    payload: DocumentUploadPayload = Form(...),
    file: UploadedFile = File(...), 
    x_brand_id: int = Header(..., alias="X-Brand-Id")
):
    tenant = get_current_tenant(request, x_brand_id)
    
    # 1. Validación de Cliente con mensaje claro
    try:
        customer = Customer.objects.get(id=payload.customer_id, brand=tenant.brand)
    except Customer.DoesNotExist:
        raise HttpError(404, f"El Cliente con ID {payload.customer_id} no existe en esta marca.")

    # 2. Validación de Tipo de Documento con mensaje claro
    try:
        doc_type = DocumentType.objects.get(id=payload.document_type_id, brand=tenant.brand)
    except DocumentType.DoesNotExist:
        raise HttpError(404, f"El Tipo de Documento con ID {payload.document_type_id} no está configurado.")
    
    try:
        with transaction.atomic():
            doc = Document(
                brand=tenant.brand,
                customer=customer,
                document_type=doc_type,
                workflow_id=payload.workflow_id,
                state_id=payload.state_id,
                created_by=request.user
            )
            
            doc.file = file
            doc.full_clean() 
            doc.save()
            
            return 201, doc
            
    except ValidationError as e:
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f"Error al registrar el documento: {str(e)}")