from ninja import Router, Query
from typing import List
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth
from dateutil.relativedelta import relativedelta
from ninja_jwt.authentication import JWTAuth

# Ajusta estas importaciones a la ruta real de tu proyecto
from workflows.models import CustomerWorkflow 
from core.dependencies import get_authorized_brands

# ¡Aquí importas los schemas que ya tienes listos!
from analytics_api.schemas import MonthlyContractStateOut, ContractSignatureStatusOut

# Protegemos el router para que request.user funcione correctamente
router = Router(auth=JWTAuth())

# ==========================================
# 1. ESTADO LEGAL DE CONTRATOS (Mensual)
# ==========================================
@router.get("/state-records", response=List[MonthlyContractStateOut])
def get_monthly_contract_states(request, brands: List[int] = Query(...)):
    """
    Desglosa los contratos de los últimos 4 meses según su etapa legal exacta:
    Borrador, En Revisión, Firmado, Rechazado.
    """
    safe_brands = get_authorized_brands(request.user, brands, required_module="contract")
    
    # Definimos la ventana temporal (Últimos 4 meses)
    today = timezone.now().date()
    months_keys = [(today - relativedelta(months=i)).replace(day=1) for i in range(3, -1, -1)]
    
    # Inicializamos el diccionario con todos los estados en 0
    data_by_month = {
        mk: {"draft": 0, "review": 0, "signed": 0, "declined": 0} 
        for mk in months_keys
    }
    
    four_months_ago = months_keys[0]

    # Agrupamos por mes y contamos los estados usando Q objects
    qs = CustomerWorkflow.objects.filter(
        workflow__brand_id__in=safe_brands,
        workflow__code='contract', 
        started_at__gte=four_months_ago
    ).annotate(
        month=TruncMonth('started_at')
    ).values('month').annotate(
        draft=Count('id', filter=Q(current_state__code='draft')),
        review=Count('id', filter=Q(current_state__code='review')),
        signed=Count('id', filter=Q(current_state__code='signed')),
        declined=Count('id', filter=Q(current_state__code='declined'))
    )

    # Poblamos el diccionario
    for item in qs:
        month_date = item['month'].date()
        if month_date in data_by_month:
            data_by_month[month_date]['draft'] = item['draft']
            data_by_month[month_date]['review'] = item['review']
            data_by_month[month_date]['signed'] = item['signed']
            data_by_month[month_date]['declined'] = item['declined']

    # Formateamos la respuesta usando tu Schema
    response_data = []
    for mk, counts in data_by_month.items():
        response_data.append({
            "mes_fecha": mk,
            "draft": counts['draft'],
            "review": counts['review'],
            "signed": counts['signed'],
            "declined": counts['declined']
        })

    return response_data


# ==========================================
# 2. ESTADO DE FIRMAS (Firmados vs Pendientes)
# ==========================================
@router.get("/signature-status", response=List[ContractSignatureStatusOut])
def get_contract_signature_status(request, brands: List[int] = Query(...)):
    """
    Compara mes a mes los contratos ya firmados vs los que siguen pendientes 
    (borrador o en revisión).
    """
    safe_brands = get_authorized_brands(request.user, brands, required_module="contract")
    
    today = timezone.now().date()
    months_keys = [(today - relativedelta(months=i)).replace(day=1) for i in range(3, -1, -1)]
    
    data_by_month = {mk: {"firmados": 0, "pendientes": 0} for mk in months_keys}
    four_months_ago = months_keys[0]

    # Agrupamos considerando "pendientes" a todo lo que no esté firmado o rechazado
    qs = CustomerWorkflow.objects.filter(
        workflow__brand_id__in=safe_brands,
        workflow__code='contract',
        started_at__gte=four_months_ago
    ).annotate(
        month=TruncMonth('started_at')
    ).values('month').annotate(
        firmados=Count('id', filter=Q(current_state__code='signed')),
        pendientes=Count('id', filter=Q(current_state__code__in=['draft', 'review']))
    )

    for item in qs:
        month_date = item['month'].date()
        if month_date in data_by_month:
            data_by_month[month_date]['firmados'] = item['firmados']
            data_by_month[month_date]['pendientes'] = item['pendientes']

    response_data = []
    for mk, counts in data_by_month.items():
        response_data.append({
            "mes_fecha": mk,
            "firmados": counts['firmados'],
            "pendientes": counts['pendientes']
        })

    return response_data