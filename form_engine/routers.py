# form_engine/routers.py
from ninja import Router, Header
from ninja.errors import HttpError
from typing import List
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.db.models import Max
from django.utils.text import slugify
from ninja_jwt.authentication import JWTAuth
from workflows.models import Workflow, WorkflowState, CustomerWorkflow
from customers.models import Customer, Contact, Company

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
    Endpoint público para recibir respuestas e inyectarlas al CRM automáticamente.
    """
    form = Form.objects.filter(
        brand_id=brand_id, 
        form_key=form_key, 
        is_public=True, 
        is_active=True
    ).order_by('-version').first()
    
    if not form:
        raise HttpError(404, "Formulario no encontrado.")
        
    with transaction.atomic():
        # 1. Guardamos la respuesta en la bandeja de formularios
        submission = FormSubmission.objects.create(
            form=form,
            payload=payload.payload,
            source=payload.source
        )
        
        # ==========================================
        # 2. EL PUENTE: CONVERSIÓN A LEAD COMERCIAL
        # ==========================================
        data = payload.payload
        
        # Extraemos los datos dinámicos
        email = data.get("email") or data.get("Correo Principal") or f"prospecto_{submission.id}@sin-correo.com"
        nombre = data.get("Nombre Completo") or "Prospecto Web"
        telefono = data.get("telefono") or data.get("Teléfono Móvil") or ""
        
        ruc = data.get("ruc") or data.get("RUC / ID Fiscal") or ""
        razon_social = data.get("razonSocial") or data.get("Razón Social") or ""

        customer = None

        # --- LÓGICA B2B vs B2C ---
        if ruc or razon_social:
            # FLUJO B2B (Empresa)
            # 1. Creamos la Empresa
            company, _ = Company.objects.get_or_create(
                brand_id=brand_id,
                tax_id=ruc or f"PENDIENTE-{submission.id}",
                defaults={
                    "legal_name": razon_social or nombre,
                    "metadata": {"origen": "Widget Web"}
                }
            )
            # 2. Creamos al Contacto y lo asociamos a la Empresa
            contact, _ = Contact.objects.get_or_create(
                brand_id=brand_id,
                email=email,
                defaults={
                    "full_name": nombre,
                    "phone": telefono,
                    "company": company,
                    "is_primary_contact": True
                }
            )
            # 3. Creamos el Nexo (Customer B2B)
            customer, _ = Customer.objects.get_or_create(
                brand_id=brand_id,
                company=company,
                defaults={
                    "customer_type": "B2B",
                    "contact": contact
                }
            )
        else:
            # FLUJO B2C (Individuo)
            # 1. Creamos solo al Contacto humano
            contact, _ = Contact.objects.get_or_create(
                brand_id=brand_id,
                email=email,
                defaults={
                    "full_name": nombre,
                    "phone": telefono
                }
            )
            # 2. Creamos el Nexo (Customer B2C)
            customer, _ = Customer.objects.get_or_create(
                brand_id=brand_id,
                contact=contact,
                customer_type="B2C"
            )

        # --- LÓGICA DE WORKFLOW (El Embudo) ---
        workflow = None
        if form.target_workflow_id:
            workflow = Workflow.objects.filter(id=form.target_workflow_id, brand_id=brand_id).first()
        
        if not workflow:
            workflow = Workflow.objects.filter(brand_id=brand_id, code='trade').first()

        if workflow and customer:
            initial_state = WorkflowState.objects.filter(workflow=workflow).order_by('sort_order').first()
            
            if initial_state:
                # Insertamos el lead en la primera etapa del tablero
                CustomerWorkflow.objects.get_or_create(
                    customer=customer,
                    workflow=workflow,
                    defaults={
                        "current_state": initial_state,
                        "metadata": data  # Toda la info extra va al tablero
                    }
                )

    return 201, {"submission_id": str(submission.submission_id)}