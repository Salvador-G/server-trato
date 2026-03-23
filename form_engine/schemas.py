# form_engine/schemas.py
from ninja import ModelSchema, Schema
from typing import List, Dict, Any, Optional
from pydantic import field_validator # <-- Importación corregida

from .models import Form, FormSubmission

# ==========================================
# 1. SCHEMAS DEL FORMULARIO (Plantilla)
# ==========================================

class FormOut(ModelSchema):
    class Meta:
        model = Form
        fields = ['id', 'form_key', 'version', 'description', 'is_public', 'is_active', 'created_at']

class FormDetailOut(ModelSchema):
    class Meta:
        model = Form
        # Cambiamos 'schema' por 'structure'
        fields = ['id', 'form_key', 'version', 'structure', 'description', 'is_public', 'is_active', 'created_at']

# En FormPublicOut actualizamos el resolver:
    @staticmethod
    def resolve_schema_fields(obj: Form) -> List[Dict[str, Any]]:
        # Asumiendo que ahora guardas la lista directa o el dict
        return obj.structure.get("schema", []) if isinstance(obj.structure, dict) else obj.structure
    
class FormCreate(Schema):
    name: str
    structure: List[Dict[str, Any]]
    description: Optional[str] = ""
    is_public: bool = False

    @classmethod # <-- Obligatorio en Pydantic V2
    @field_validator('structure') # <-- Decorador actualizado
    def validate_schema_structure(cls, v):
        for field in v:
            if 'id' not in field or 'type' not in field:
                raise ValueError("Cada campo dentro del schema debe tener 'id' y 'type'")
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
        return obj.schema.get("schema", []) if isinstance(obj.schema, dict) else obj.schema

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
    # No pedimos el form_id ni el source aquí, los sacaremos de la URL y del endpoint público