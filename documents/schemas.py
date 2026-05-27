# documents/schemas.py
from ninja import ModelSchema, Schema
from typing import Optional, List
from .models import Document, DocumentType

class DocumentTypeOut(ModelSchema):
    class Meta:
        model = DocumentType
        fields = ['id', 'code', 'name']

class DocumentOut(ModelSchema):
    document_type: DocumentTypeOut
    file_url: Optional[str] = None
    uploaded_by_name: str = "Sistema"

    class Meta:
        model = Document
        fields = ['id', 'customer', 'workflow', 'state', 'mime_type', 'created_at']

    @staticmethod
    def resolve_file_url(obj: Document) -> Optional[str]:
        return obj.file.url if obj.file else None

    @staticmethod
    def resolve_uploaded_by_name(obj: Document) -> str:
        if obj.created_by:
            full_name = f"{obj.created_by.first_name} {obj.created_by.last_name}".strip()
            return full_name if full_name else obj.created_by.email
        return "Sistema"

class DocumentUploadPayload(Schema):
    """Payload para enviar junto al archivo multipart/form-data"""
    customer_id: int
    document_type_code: str
    workflow_id: Optional[int] = None
    state_id: Optional[int] = None