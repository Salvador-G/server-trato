```python
from django.db import models
from django.conf import settings
import uuid

# =========================
# FORM
# =========================
class Form(models.Model):
    brand = models.ForeignKey(
        "core.Brand",
        on_delete=models.CASCADE,
        related_name="forms"
    )

    form_key = models.SlugField(help_text="Slug o ID público del formulario")
    
    structure = models.JSONField(help_text="Estructura en JSON del formulario")
    
    target_workflow = models.ForeignKey(
        "workflows.Workflow", 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name="linked_forms",
        help_text="¿A qué flujo se enviarán los datos? (Por defecto: Comercial)"
    )
    
    version = models.PositiveIntegerField(default=1)
    description = models.CharField(max_length=255, blank=True)
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,   
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("brand", "form_key", "version")
        ordering = ["-version"]
        verbose_name = "Form"
        verbose_name_plural = "Forms"

    def __str__(self):
        return f"{self.form_key} v{self.version} ({self.brand.name})"

# =========================
# FORM SUBMISSION
# =========================
class FormSubmission(models.Model):
    SOURCE_CHOICES = (
        ("widget", "Widget"),
        ("iframe", "Iframe HTML"),
        ("internal", "Internal"),
        ("api", "API"),
    )

    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="submissions"
    )

    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="form_submissions"
    )

    submission_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    payload = models.JSONField(help_text="Respuestas enviadas en JSON")
    
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Form Submission"
        verbose_name_plural = "Form Submissions"

    def __str__(self):
        return str(self.submission_id)


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


# form_engine/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.db.models import Max
from django.utils.text import slugify
from ninja_jwt.authentication import JWTAuth
from workflows.models import Workflow

from .models import Form, FormSubmission
from .schemas import (
    FormOut, FormCreate, FormDetailOut,
    FormPublicOut, FormSubmissionCreate, FormSubmissionOut
)
from core.dependencies import get_current_tenant

# Protegemos el router por defecto para el panel de administración
router = Router(tags=["Form Engine"], auth=JWTAuth())

# ==========================================
# ENDPOINTS PRIVADOS (Panel de Control SaaS)
# ==========================================

@router.get("/", response={200: List[FormOut]})
def list_forms(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Lista todos los formularios de la marca actual."""
    tenant = get_current_tenant(request, x_brand_id)
    # A diferencia de tu DRF (que filtraba por user), aquí filtramos por marca 
    # para que todo el equipo vea los formularios de la empresa
    return Form.objects.filter(brand=tenant.brand).order_by("-created_at")

@router.post("/", response={201: FormOut})
def create_form(request, payload: FormCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Crea un formulario nuevo, autogenerando el slug y la versión."""
    tenant = get_current_tenant(request, x_brand_id)
    
    # Generamos el slug a partir del nombre
    form_key = slugify(payload.name)
    
    # Buscamos la última versión
    last_version_dict = Form.objects.filter(brand=tenant.brand, form_key=form_key).aggregate(Max('version'))
    last_version = last_version_dict.get('version__max') or 0
    new_version = last_version + 1
    
    # Apagamos las versiones anteriores de ESTE form_key para evitar conflictos
    if last_version > 0:
        Form.objects.filter(brand=tenant.brand, form_key=form_key).update(is_active=False, is_public=False)
    
    # 🔥 BLINDAJE SAAS: Verificamos que si envían un target_workflow_id, pertenezca a SU marca
    if payload.target_workflow_id:
        if not Workflow.objects.filter(id=payload.target_workflow_id, brand=tenant.brand).exists():
            raise HttpError(400, "El proceso seleccionado no es válido o no pertenece a tu cuenta.")

    # Creamos la nueva versión oficial
    form = Form.objects.create(
        brand=tenant.brand,
        form_key=form_key,
        version=new_version,
        structure={"schema": payload.structure}, 
        description=payload.description,
        is_public=payload.is_public,
        target_workflow_id=payload.target_workflow_id, # 🔥 NUEVO: Asignamos el campo
        created_by=request.user
    )
    return 201, form

@router.get("/submissions", response=List[FormSubmissionOut])
def list_submissions(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Lista todos los leads (submissions) capturados para la marca actual."""
    tenant = get_current_tenant(request, x_brand_id)
    
    # Gracias al Schema, solo necesitamos retornar el QuerySet directo
    return FormSubmission.objects.filter(
        form__brand=tenant.brand
    ).select_related('form').order_by('-submitted_at')
    
    
@router.get("/{form_id}", response=FormDetailOut)
def get_form_detail(request, form_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """Obtiene el JSON completo de un formulario para editarlo en el builder."""
    tenant = get_current_tenant(request, x_brand_id)
    return get_object_or_404(Form, id=form_id, brand=tenant.brand)


# ==========================================
# ENDPOINTS PÚBLICOS (Para el Widget / Vue)
# ¡Ojo aquí! Usamos auth=None para permitir AllowAny
# ==========================================

@router.get("/public/{brand_id}/{form_key}", response=FormPublicOut, auth=None)
def get_public_form(request, brand_id: int, form_key: str):
    """
    Endpoint público para que el widget de Vue dibuje el formulario.
    No requiere Token ni cabecera X-Brand-Id.
    """
    # Buscamos la ÚLTIMA versión activa y pública de ese form_key
    form = Form.objects.filter(
        brand_id=brand_id, 
        form_key=form_key, 
        is_public=True, 
        is_active=True
    ).order_by('-version').first()
    
    if not form:
        raise HttpError(404, "Formulario no encontrado o no está disponible.")
        
    return form

@router.post("/public/{brand_id}/{form_key}/submit", response={201: dict}, auth=None)
def submit_public_form(request, brand_id: int, form_key: str, payload: FormSubmissionCreate):
    """
    Endpoint público para recibir las respuestas del cliente final.
    """
    # Verificamos que el formulario exista y esté abierto
    form = Form.objects.filter(
        brand_id=brand_id, 
        form_key=form_key, 
        is_public=True, 
        is_active=True
    ).order_by('-version').first()
    
    if not form:
        raise HttpError(404, "Formulario no encontrado.")
        
    # Guardamos la respuesta
    submission = FormSubmission.objects.create(
        form=form,
        payload=payload.payload,
        source=payload.source
    )
    
    return 201, {"submission_id": str(submission.submission_id)}
```