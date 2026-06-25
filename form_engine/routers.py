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

    # ==========================================
    # 1. FILTRO ANTI-VACÍO (Anti-Spam Básico)
    # ==========================================
    # Limpiamos el payload de nulos o strings vacíos
    datos_limpios = {
        k: v for k, v in payload.payload.items() 
        if v is not None and str(v).strip() != ""
    }

    if not datos_limpios:
        raise HttpError(400, "El formulario no puede enviarse completamente vacío.")

    # ==========================================
    # 2. VALIDACIÓN DINÁMICA DE REGLAS
    # ==========================================
    # Asumiendo que tu modelo Form tiene un campo JSON (ej. `fields_config`) 
    # donde guardas la estructura de los campos que el tenant configuró.
    errores_validacion = {}
    
    if hasattr(form, 'fields_config') and form.fields_config:
        for campo in form.fields_config:
            # Ignoramos campos que son meramente para visualización estática en el front
            if campo.get('is_static_display'):
                continue
                
            nombre_campo = campo.get('name')
            es_requerido = campo.get('required', False)
            valor_recibido = datos_limpios.get(nombre_campo)

            if es_requerido and not valor_recibido:
                errores_validacion[nombre_campo] = "Este campo es obligatorio."
                
    if errores_validacion:
        # Detenemos el flujo y le avisamos al front exactamente qué falló
        raise HttpError(400, {"mensaje": "Errores de validación", "detalles": errores_validacion})

    # ==========================================
    # 3. GUARDADO Y PUENTE COMERCIAL
    # ==========================================
    with transaction.atomic():
        # Guardamos la respuesta usando la data YA LIMPIA
        submission = FormSubmission.objects.create(
            form=form,
            payload=datos_limpios, # Reemplazamos el raw por los datos limpios
            source=payload.source
        )
        
        # Extraemos los datos dinámicos usando los datos limpios
        email = datos_limpios.get("email") or datos_limpios.get("Correo Principal") or f"prospecto_{submission.id}@sin-correo.com"
        nombre = datos_limpios.get("Nombre Completo") or "Prospecto Web"
        telefono = datos_limpios.get("telefono") or datos_limpios.get("Teléfono Móvil") or ""
        
        ruc = datos_limpios.get("ruc") or datos_limpios.get("RUC / ID Fiscal") or ""
        razon_social = datos_limpios.get("razonSocial") or datos_limpios.get("Razón Social") or ""

        customer = None

        # --- LÓGICA B2B vs B2C ---
        if ruc or razon_social:
            # FLUJO B2B (Empresa)
            company, _ = Company.objects.get_or_create(
                brand_id=brand_id,
                tax_id=ruc or f"PENDIENTE-{submission.id}",
                defaults={
                    "legal_name": razon_social or nombre,
                    "metadata": {"origen": "Widget Web"}
                }
            )
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
            contact, _ = Contact.objects.get_or_create(
                brand_id=brand_id,
                email=email,
                defaults={
                    "full_name": nombre,
                    "phone": telefono
                }
            )
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
                # Inyectamos el form_key en la data para saber de qué formulario vino
                datos_limpios["form_source_key"] = form.form_key 
                
                solicitud_activa = CustomerWorkflow.objects.filter(
                    customer=customer,
                    workflow=workflow,
                    finished_at__isnull=True,
                    metadata__form_source_key=form.form_key
                ).exists()

                if not solicitud_activa:
                    CustomerWorkflow.objects.create(
                        customer=customer,
                        workflow=workflow,
                        current_state=initial_state,
                        metadata=datos_limpios
                    )

    return 201, {"submission_id": str(submission.submission_id)}