```python
# modules_api/schemas.py
from datetime import datetime

from ninja import Schema
from typing import Optional, List, Dict, Any

class AsideContactInfo(Schema):
    phone: str
    email: str
    interaction_method: str

class AsideRequirementDetails(Schema):
    ruc: str
    service: str
    period: str
    original_message: str

class SharedAsideOut(Schema):
    """Esquema diseñado específicamente para la columna izquierda de PrimeVue"""
    estado_actual: str
    esperando_respuesta: bool
    
    # Cabecera
    contact_name: str
    company_name: str
    
    # Secciones
    contact_info: AsideContactInfo
    requirement_details: AsideRequirementDetails
    
# ==========================================
# SCHEMAS: TRADE (Ventas - Columna Derecha)
# ==========================================

class TradeListRowOut(Schema):
    """Esquema diseñado para la tabla/Datatable de TradeList.vue"""
    id: int
    fecha: datetime
    ruc: str
    razonSocial: str
    personal: str
    estadoId: str
    
class TradeStepOut(Schema):
    """Para el Stepper Horizontal (Pipeline)"""
    nombre: str
    estado: str  # Valores CSS: 'completado', 'pendiente' (Vue manejará la opacidad)
    fecha: Optional[datetime] = None
    tipo: str = "envio" # Opcional para iconos

class TradeTimelineEvent(Schema):
    """Para el PrimeVue Timeline Vertical (Feed de actividad)"""
    status: str       # Ej: 'Lead creado', 'Correo enviado', 'Cliente respondió'
    description: str  # Ej: 'a través de Página Web', 'Asunto: Cotización'
    date: datetime         # Ej: '17/12/2025 - 10:30 AM'
    color: str        # Ej: '#10b981' (verde), '#3b82f6' (azul)
    body: Optional[str] = None

class TradeEmailDraft(Schema):
    """Para la tarjeta de Redactar Mensaje"""
    to: str
    subject: str
    body: str

class TradeMainOut(Schema):
    """El payload maestro para la vista TradeView.vue (main tag)"""
    esperandoRespuesta: bool
    historialPasos: List[TradeStepOut]
    historyEvents: List[TradeTimelineEvent]
    emailDraft: TradeEmailDraft
    assigned_to_id: Optional[int] = None
    assigned_to_name: Optional[str] = None
    current_user_id: int
    
class ManualTradeCreate(Schema):
    # --- 1. DATOS DUROS (Entidades SQL) ---
    ruc: str
    razonSocial: str
    personaContacto: str
    correo: str
    telefono: str
    
    # --- 2. METADATA DINÁMICA (JSON) ---
    # En lugar de tipar campo por campo comercial, recibimos un diccionario.
    # Así, si mañana en Vue agregas "presupuesto", no tienes que tocar este archivo.
    detalles_comerciales: Dict[str, Any] = {}


# modules_api/routers/shared.py
from ninja import Router, Header
from django.shortcuts import get_object_or_404
from ninja_jwt.authentication import JWTAuth

from workflows.models import CustomerWorkflow
from core.dependencies import get_current_tenant
from ..schemas import SharedAsideOut

router = Router(tags=["Modules API - Shared UI"], auth=JWTAuth())

@router.get("/aside/{cw_id}", response=SharedAsideOut)
def get_shared_aside_data(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la data formateada exactamente como la necesita 
    el <aside> de Vue 3 (Trade, Contract, Support).
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    # Traemos el workflow con sus relaciones optimizadas
    cw = get_object_or_404(
        CustomerWorkflow.objects.select_related(
            'current_state', 
            'customer__company', 
            'customer__contact'
        ), 
        id=cw_id, 
        workflow__brand=tenant.brand
    )
    
    customer = cw.customer
    metadata = cw.metadata or {}

    # Manejo seguro de nulos (por si es B2B sin contacto, o B2C sin empresa)
    contact_name = customer.contact.full_name if customer.contact else "Sin contacto asignado"
    contact_phone = customer.contact.phone if customer.contact else "No registrado"
    contact_email = customer.contact.email if customer.contact else "No registrado"
    
    company_name = customer.company.legal_name if customer.company else "Cliente Independiente"
    company_ruc = customer.company.tax_id if customer.company else "No aplica"

    # Lógica de UI: ¿Estamos esperando al cliente? 
    # Podrías basarlo en un flag del estado, o en el código del estado
    esperando_respuesta = cw.current_state.code in ['waiting_client', 'pending_info']

    # Armamos la respuesta a medida del frontend
    return {
        "estado_actual": cw.current_state.name,
        "esperando_respuesta": esperando_respuesta,
        "contact_name": contact_name,
        "company_name": company_name,
        "contact_info": {
            "phone": contact_phone,
            "email": contact_email,
            "interaction_method": metadata.get("source", "Página Web")
        },
        "requirement_details": {
            "ruc": company_ruc,
            "service": metadata.get("servicio_requerido", "No especificado"),
            "period": metadata.get("periodo", "No especificado"),
            "original_message": metadata.get("mensaje_original", "Sin mensaje inicial.")
        }
    }


# modules_api/routers/trade.py
from ninja import Router, Header
from ninja.errors import HttpError
from django.db import transaction
from django.shortcuts import get_object_or_404
from ninja_jwt.authentication import JWTAuth
from django.utils.timezone import localtime
from itertools import chain
from operator import attrgetter
from typing import List

from workflows.models import CustomerWorkflow, CustomerWorkflowHistory, Workflow
from customers.models import Company, Contact, Customer
from communications.models import Message
from core.dependencies import get_current_tenant
from ..schemas import TradeMainOut, TradeListRowOut, ManualTradeCreate

router = Router(tags=["Modules API - Trade (Ventas)"], auth=JWTAuth())

@router.get("/active", response=List[TradeListRowOut])
def list_active_trades(request, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    """
    Devuelve la lista de oportunidades de venta activas.
    Reemplaza al antiguo llamado a form_engine/submissions.
    """
    tenant = get_current_tenant(request, x_brand_id)
    
    # Filtramos: Solo la marca actual, solo el workflow de 'trade', y que no estén finalizados
    cws = CustomerWorkflow.objects.filter(
        workflow__brand=tenant.brand,
        workflow__code='trade', 
        finished_at__isnull=True
    ).select_related(
        'customer__company', 
        'customer__contact',
        'assigned_to', 
        'current_state'
    ).order_by('-started_at')

    resultados = []
    
    for cw in cws:
        cliente = cw.customer
        empresa = cliente.company
        
        # Lógica de fallback por si es B2C
        ruc = empresa.tax_id if empresa else "N/A"
        razon_social = empresa.legal_name if empresa else (cliente.contact.full_name if cliente.contact else "Sin Nombre")
        
        # Personal asignado
        if cw.assigned_to:
            personal = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email
        else:
            personal = "Sin asignar"

        # CORRECCIÓN: Eliminamos el strftime y pasamos el objeto datetime crudo
        resultados.append({
            "id": cw.id,
            "fecha": cw.started_at, # <--- ¡Solo esto!
            "ruc": ruc,
            "razonSocial": razon_social,
            "personal": personal,
            "estadoId": cw.current_state.code 
        })

    return resultados

@router.get("/active/{cw_id}/main", response=TradeMainOut)
def get_trade_main_data(request, cw_id: int, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    
    # 1. Traemos el contexto principal
    cw = get_object_or_404(
        CustomerWorkflow.objects.select_related(
            'workflow', 'current_state', 'customer__contact'
        ), 
        id=cw_id, 
        workflow__brand=tenant.brand
    )

    metadata = cw.metadata or {}
    contact_email = cw.customer.contact.email if cw.customer.contact else ""
    
    # ---------------------------------------------------------
    # A. PIPELINE DE PASOS (Stepper)
    # ---------------------------------------------------------
    historial_pasos = []
    current_order = cw.current_state.sort_order
    all_states = cw.workflow.states.all().order_by('sort_order')
    
    history_logs = list(cw.history_logs.all())
    
    # CORRECCIÓN 1: Enviar el datetime crudo, sin strftime ni localtime
    history_dates = {
        log.state_id: log.changed_at 
        for log in sorted(history_logs, key=lambda x: x.changed_at)
    }

    for state in all_states:
        is_past = state.sort_order <= current_order
        historial_pasos.append({
            "nombre": state.name,
            "estado": "completado" if is_past else "pendiente",
            # Si hay fecha, enviamos el datetime crudo. Si no, un string vacío (o None).
            "fecha": history_dates.get(state.id, None), 
            "tipo": "envio" 
        })

    # ---------------------------------------------------------
    # B. HISTORIAL OMNICANAL (Workflow Logs + Emails)
    # ---------------------------------------------------------
    history_events = []
    
    messages = Message.objects.filter(
        conversation__customer_workflow=cw
    ).select_related('conversation')

    combined_timeline = sorted(
        chain(history_logs, messages),
        key=lambda obj: obj.changed_at if hasattr(obj, 'changed_at') else obj.created_at,
        reverse=True
    )

    for item in combined_timeline:
        if hasattr(item, 'state'):
            color = "#10b981" if item.state.is_final else "#d1d5db"
            history_events.append({
                "status": f"Estado: {item.state.name}",
                "description": item.comment or "Actualización de flujo.",
                # CORRECCIÓN 2: Enviar el datetime crudo
                "date": item.changed_at, 
                "color": color
            })
        else:
            is_inbound = item.direction == 'inbound'
            color = "#f59e0b" if is_inbound else "#3b82f6"
            status_text = "Cliente respondió" if is_inbound else "Correo enviado"
            
            history_events.append({
                "status": status_text,
                "description": f"Asunto: {item.subject or 'Sin asunto'}",
                "body": item.body if hasattr(item, 'body') else None,
                # CORRECCIÓN 3: Enviar el datetime crudo
                "date": item.created_at, 
                "color": color
            })

    # ---------------------------------------------------------
    # C. REDACTAR CORREO (Draft Inicial)
    # ---------------------------------------------------------
    esperando_respuesta = cw.current_state.code in ['waiting_client', 'pending_info']
    servicio = metadata.get("servicio_requerido", "")
    asunto = f"Cotización - {servicio}" if servicio else "Atención a su requerimiento"
    
    email_draft = {
        "to": contact_email,
        "subject": asunto,
        "body": "Estimados,\n\nBuen día, por medio de la presente..."
    }

    assigned_id = cw.assigned_to_id
    assigned_name = None
    if cw.assigned_to:
        assigned_name = f"{cw.assigned_to.first_name} {cw.assigned_to.last_name}".strip() or cw.assigned_to.email

    return {
        "esperandoRespuesta": esperando_respuesta,
        "historialPasos": historial_pasos,
        "historyEvents": history_events,
        "emailDraft": email_draft,
        # Agregamos la metadata de propiedad
        "assigned_to_id": assigned_id,
        "assigned_to_name": assigned_name,
        "current_user_id": request.user.id
    }
    
        
    
@router.post("/manual", response={201: dict})
def create_manual_trade(request, payload: ManualTradeCreate, x_brand_id: int = Header(..., alias="X-Brand-Id")):
    tenant = get_current_tenant(request, x_brand_id)
    brand = tenant.brand

    with transaction.atomic():
        # 1. DATOS DUROS: Tablas SQL (Manejo a prueba de duplicados)
        
        # --- COMPANY ---
        company = Company.objects.filter(brand=brand, tax_id=payload.ruc).first()
        if not company:
            company = Company.objects.create(
                brand=brand, 
                tax_id=payload.ruc, 
                legal_name=payload.razonSocial
            )

        # --- CONTACT ---
        contact = Contact.objects.filter(brand=brand, email=payload.correo).first()
        if not contact:
            contact = Contact.objects.create(
                brand=brand, 
                email=payload.correo,
                full_name=payload.personaContacto, 
                phone=payload.telefono, 
                company=company,
                is_primary_contact=True
            )

        # --- CUSTOMER ---
        customer = Customer.objects.filter(brand=brand, company=company).first()
        if not customer:
            customer = Customer.objects.create(
                brand=brand, 
                company=company,
                customer_type='B2B', 
                contact=contact
            )

        # 2. METADATA: Inyectamos el JSON tal cual vino del frontend
        workflow = get_object_or_404(Workflow, code='trade', brand=brand)
        initial_state = workflow.states.order_by('sort_order').first()

        cw = CustomerWorkflow.objects.create(
            customer=customer,
            workflow=workflow,
            current_state=initial_state,
            assigned_to=request.user,
            metadata=payload.detalles_comerciales # <--- ¡Aquí ocurre la magia!
        )

        CustomerWorkflowHistory.objects.create(
            customer_workflow=cw,
            state=initial_state,
            user=request.user,
            comment="Ingresado manualmente por el equipo."
        )

    return 201, {"message": "Oportunidad creada con éxito", "cw_id": cw.id}

```