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