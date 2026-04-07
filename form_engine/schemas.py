# form_engine/schemas.py
from uuid import UUID
from datetime import datetime
from ninja import ModelSchema, Schema
from typing import List, Dict, Any, Optional
from pydantic import field_validator 

from .models import Form, FormSubmission

# ==========================================
# 1. SCHEMAS DEL FORMULARIO (Plantilla)
# ==========================================

class FormOut(ModelSchema):
    
    target_workflow_id: Optional[int] = None
    
    class Meta:
        model = Form
        fields = ['id', 'form_key', 'version', 'description', 'is_public', 'is_active', 'created_at']

class FormDetailOut(ModelSchema):
    
    target_workflow_id: Optional[int] = None
    
    class Meta:
        model = Form
        fields = ['id', 'form_key', 'version', 'structure', 'description', 'is_public', 'is_active', 'created_at']

class FormCreate(Schema):
    name: str
    structure: List[Dict[str, Any]]
    description: Optional[str] = ""
    is_public: bool = False

    target_workflow_id: Optional[int] = None
    
    @field_validator('structure')
    @classmethod # Pydantic V2 requiere @classmethod después de @field_validator
    def validate_schema_structure(cls, v):
        for field in v:
            if 'id' not in field or 'type' not in field:
                raise ValueError("Cada campo dentro de la estructura debe tener 'id' y 'type'")
        return v

# ==========================================
# 2. SCHEMA PÚBLICO (Para el Widget Vue)
# ==========================================

class FormPublicMeta(Schema):
    brand_name: str
    form_key: str

class FormPublicOut(Schema):
    form_key: str
    version: int
    schema_fields: List[Dict[str, Any]]
    meta: FormPublicMeta

    @staticmethod
    def resolve_schema_fields(obj: Form) -> List[Dict[str, Any]]:
        # ¡CORREGIDO! Antes decía obj.schema, pero tu modelo ahora usa obj.structure
        if isinstance(obj.structure, dict):
            return obj.structure.get("schema", [])
        return obj.structure

    @staticmethod
    def resolve_meta(obj: Form) -> dict:
        return {
            "brand_name": obj.brand.name,
            "form_key": obj.form_key,
        }

# ==========================================
# 3. SCHEMAS DE RESPUESTAS (Submissions)
# ==========================================

class FormSubmissionCreate(Schema):
    payload: Dict[str, Any]
    # No pedimos el form_id ni el source aquí, los sacamos de la URL y del endpoint
    source: str = "widget" # default
    
class FormSubmissionOut(Schema):
    id: UUID
    form_name: str
    source: str
    submitted_at: datetime
    payload: Dict[str, Any]

    @staticmethod
    def resolve_id(obj: FormSubmission):
        # Mapeamos submission_id a "id" para que Vue lo lea fácil
        return obj.submission_id

    @staticmethod
    def resolve_form_name(obj: FormSubmission):
        # Extraemos el nombre del formulario relacionado
        return obj.form.form_key