from ninja import Router, Query
from typing import List
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from dateutil.relativedelta import relativedelta

# Importamos tu modelo real de la app workflows
from workflows.models import CustomerWorkflow 

# Importamos los schemas que devolverán la data a Vue
from analytics_api.schemas import TradeFunnelOut, MonthlyRecordPercentageOut
from core.dependencies import get_authorized_brands

router = Router()

# ==========================================
# 1. ESTADO DEL EMBUDO COMERCIAL (Gráfico de Barras)
# ==========================================
@router.get("/status", response=TradeFunnelOut)
def get_trade_status(request, brands: List[int] = Query(...)):
    """
    Devuelve la cantidad de leads agrupados por su estado comercial actual.
    Filtra dinámicamente usando el Multi-Tenant (brands).
    """
    
    safe_brands = get_authorized_brands(request.user, brands, required_module="trade")
    
    # Filtramos la tabla general aislando solo los flujos comerciales de las marcas
    base_query = CustomerWorkflow.objects.filter(
        workflow__brand_id__in=safe_brands,
        workflow__code='trade'
    )
    
    # Agregación en un solo query hacia la base de datos usando la relación current_state
    stats = base_query.aggregate(
        prospecto=Count('id', filter=Q(current_state__code='lead')),
        negotiation=Count('id', filter=Q(current_state__code='negotiation')),
        won=Count('id', filter=Q(current_state__code='won')),
        lost=Count('id', filter=Q(current_state__code='lost')),
    )
    
    return {
        "prospecto": stats["prospecto"] or 0,
        "negotiation": stats["negotiation"] or 0,
        "won": stats["won"] or 0,
        "lost": stats["lost"] or 0,
    }

# ==========================================
# 2. REGISTROS MENSUALES (Gráfico de Dona / Porcentajes)
# ==========================================
@router.get("/monthly-records", response=List[MonthlyRecordPercentageOut])
def get_trade_monthly_records(request, brands: List[int] = Query(...)):
    """
    Obtiene la distribución porcentual de los nuevos leads 
    (workflows comerciales) generados en los últimos 6 meses.
    """
    
    # Definir la ventana temporal (Últimos 6 meses)
    today = timezone.now().date()
    months_keys = [(today - relativedelta(months=i)).replace(day=1) for i in range(5, -1, -1)]
    counts_by_month = {mk: 0 for mk in months_keys}
    six_months_ago = months_keys[0]

    # Consulta a la BD con el filtro exclusivo de TRADE
    qs = CustomerWorkflow.objects.filter(
        workflow__brand_id__in=brands,
        workflow__code='trade',
        started_at__gte=six_months_ago
    ).annotate(
        month=TruncMonth('started_at')
    ).values('month').annotate(
        total=Count('id')
    )

    # Poblamos los datos asegurando que los meses con 0 leads no desaparezcan
    for item in qs:
        month_date = item['month'].date() 
        if month_date in counts_by_month:
            counts_by_month[month_date] = item['total']

    # Cálculo matemático de porcentajes
    total_records = sum(counts_by_month.values())
    
    response_data = []
    for mk, count in counts_by_month.items():
        pct = round((count / total_records) * 100, 1) if total_records > 0 else 0.0
        
        response_data.append({
            "mes_fecha": mk,
            "porcentaje": pct
        })

    return response_data