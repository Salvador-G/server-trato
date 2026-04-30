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
    
# ================================================
# SCHEMAS: CONTRACT (Contratos - Columna Derecha)
# ================================================

class ContractListRowOut(Schema):
    """Esquema para cada fila de la tabla en ContractList"""
    id: int
    fecha: datetime
    ruc: str
    razonSocial: str
    personal: str
    estadoId: str
    
# ================================================
# SCHEMAS: BILLING (Facturación - Columna Derecha)
# ================================================

class BillingListRowOut(Schema):
    """Esquema para cada fila de la tabla en BillingList"""
    id: int
    fecha: datetime
    ruc: str
    razonSocial: str
    personal: str
    estadoId: str
    
# ================================================
# SCHEMAS: SUPPORT (Soporte / Onboarding - Columna Derecha)
# ================================================

class SupportListRowOut(Schema):
    """Esquema para cada fila de la tabla en SupportList"""
    id: int
    fecha: datetime
    ruc: str
    razonSocial: str
    personal: str
    estadoId: str