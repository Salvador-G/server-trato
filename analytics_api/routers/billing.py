from ninja import Router, Query
from typing import List
from django.utils import timezone
from dateutil.relativedelta import relativedelta
from ninja_jwt.authentication import JWTAuth

# Ajusta las importaciones a tus rutas
from workflows.models import CustomerWorkflow 
from core.dependencies import get_authorized_brands
from analytics_api.schemas import MonthlyBillingOut

router = Router(auth=JWTAuth())

@router.get("/paid-records", response=List[MonthlyBillingOut])
def get_monthly_billing_records(request, brands: List[int] = Query(...)):
    """
    Obtiene la facturación pagada de los últimos 4 meses.
    Extrae el dinero del campo JSON 'metadata'.
    """
    safe_brands = get_authorized_brands(request.user, brands, required_module="billing")
    
    today = timezone.now().date()
    months_keys = [(today - relativedelta(months=i)).replace(day=1) for i in range(3, -1, -1)]
    
    data_by_month = {mk: 0.0 for mk in months_keys}
    four_months_ago = months_keys[0]

    # Asumimos que quieres solo los workflows en estado 'pagado' (paid)
    qs = CustomerWorkflow.objects.filter(
        workflow__brand_id__in=safe_brands,
        workflow__code='billing', 
        current_state__code='paid', # <-- Ajusta este código a tu estado de éxito
        started_at__gte=four_months_ago
    )

    for item in qs:
        month_date = item.started_at.date().replace(day=1)
        if month_date in data_by_month:
            # Extraemos del JSONField
            metadata = item.metadata or {}
            # CAMBIA 'monto' por el nombre exacto de la llave en tu JSON
            monto_str = metadata.get('monto', 0) 
            try:
                monto_float = float(monto_str)
            except (ValueError, TypeError):
                monto_float = 0.0
                
            data_by_month[month_date] += monto_float

    response_data = []
    for mk, total in data_by_month.items():
        response_data.append({
            "mes_fecha": mk,
            "monto": round(total, 2)
        })

    return response_data