from ninja import Schema
from datetime import date
from typing import List

# ==========================================
# 1. SCHEMAS: TRADE (Comercial / Ventas)
# ==========================================

class MonthlyRecordPercentageOut(Schema):
    """
    Schema para la gráfica de dona (Registros Mensuales).
    Devuelve la fecha del mes y el porcentaje matemático calculado.
    """
    mes_fecha: date
    porcentaje: float

class TradeFunnelOut(Schema):
    """
    Schema para la gráfica de barras horizontales (Estados de Gestión Comercial).
    Devuelve los totales absolutos del embudo actual.
    """
    prospecto: int
    negotiation: int
    won: int
    lost: int


# ==========================================
# 2. SCHEMAS: CONTRACT (Legal / Contratos)
# ==========================================

class MonthlyContractStateOut(Schema):
    """
    Schema para la gráfica de barras apiladas (Estado Legal de Contratos).
    A diferencia de trade, aquí devolvemos los estados agrupados por cada mes.
    """
    mes_fecha: date
    draft: int
    review: int
    signed: int
    declined: int

class ContractSignatureStatusOut(Schema):
    """
    Schema para la gráfica de barras agrupadas (Estado de Firmas).
    Compara mes a mes los contratos exitosos vs los pendientes de firma.
    """
    mes_fecha: date
    firmados: int
    pendientes: int


# ==========================================
# 3. SCHEMAS: BILLING (Facturación)
# ==========================================

class MonthlyBillingOut(Schema):
    """
    Schema para la lista tabulada (Facturación Pagada).
    Extrae el dinero del JSONField 'metadata'.
    """
    mes_fecha: date
    monto: float