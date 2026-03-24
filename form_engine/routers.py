# form_engine/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.shortcuts import get_object_or_404
from django.db.models import Max
from django.utils.text import slugify
from ninja_jwt.authentication import JWTAuth

from .models import Form, FormSubmission
from .schemas import (
    FormOut, FormCreate, FormDetailOut,
    FormPublicOut, FormSubmissionCreate
)
from core.dependencies import get_current_tenant

# Protegemos el router por defecto para el panel de administración
router = Router(tags=["Form Engine"], auth=JWTAuth())

# ==========================================
# ENDPOINTS PRIVADOS (Panel de Control SaaS)
# ==========================================

@router.get("/", response=List[FormOut])
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
    
    # Generamos el slug a partir del nombre (Si envían 'untitled-form', el slug será ese)
    form_key = slugify(payload.name)
    
    # Buscamos la última versión
    last_version_dict = Form.objects.filter(brand=tenant.brand, form_key=form_key).aggregate(Max('version'))
    last_version = last_version_dict.get('version__max') or 0
    new_version = last_version + 1
    
    # ¡NUEVO! Apagamos las versiones anteriores de ESTE form_key para evitar conflictos
    if last_version > 0:
        Form.objects.filter(brand=tenant.brand, form_key=form_key).update(is_active=False, is_public=False)
    
    # Creamos la nueva versión oficial
    form = Form.objects.create(
        brand=tenant.brand,
        form_key=form_key,
        version=new_version,
        structure={"schema": payload.structure}, 
        description=payload.description,
        is_public=payload.is_public,
        created_by=request.user
    )
    return 201, form

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
        source="widget" # Fijamos la fuente tal como lo hacía tu APIView
    )
    
    return 201, {"submission_id": str(submission.submission_id)}