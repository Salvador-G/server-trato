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
    
    customer = get_object_or_404(Customer, id=payload.customer_id, brand=tenant.brand)
    doc_type = get_object_or_404(DocumentType, id=payload.document_type_id, brand=tenant.brand)
    
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
            
            # 1. Asignamos el archivo en MEMORIA (Todavía no se guarda en disco)
            doc.file = file
            
            # 2. Forzamos la validación. ¡Aquí se dispara nuestro escáner (MIME, Hash, Pillow)!
            # Si detecta malware, lanza un error y el proceso muere aquí sin tocar el disco duro.
            doc.full_clean() 
            
            # 3. Si sobrevivió el escáner, guardamos. 
            # Django ahora sí lo escribe en el disco usando el upload_to de forma segura.
            doc.save()
            
            return 201, doc
            
    except ValidationError as e:
        # Errores de validación (MIME, Duplicados, etc)
        raise HttpError(400, str(e))
    except Exception as e:
        raise HttpError(500, f"Error al registrar el documento: {str(e)}")