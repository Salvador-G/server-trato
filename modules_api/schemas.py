# modules_api/schemas.py
from datetime import datetime

from ninja import Schema, ModelSchema
from typing import Optional, List, Dict, Any
from core.models import AuditLog

# Schema de salida para los logs de auditoría, con campos relevantes para el frontend
class AuditLogOut(ModelSchema):
    class Meta:
        model = AuditLog
        fields = ['id', 'action', 'details', 'ip_address', 'user_agent', 'created_at']
        
class UserDetailExtendedOut(Schema):
    id: int
    email: str
    first_name: str
    last_name: str
    is_active: bool
    joined_at: datetime
    role_name: str
    
    # Datos del perfil (pueden ser nulos si no los llenó)
    document_type: Optional[str] = None
    document_id: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
        
# Schema general para los modulos operativos (Trade, Contract, Billing, Support)
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
# 1. ESQUEMA BASE (El motor de traducción)
# ==========================================
class BaseListRowOut(Schema):
    """Esquema padre que tiene la lógica para extraer datos del CustomerWorkflow"""
    id: int
    fecha: datetime
    ruc: str
    razonSocial: str
    personal: str
    estadoId: str

    @staticmethod
    def resolve_fecha(obj):
        return obj.started_at

    @staticmethod
    def resolve_ruc(obj):
        empresa = obj.customer.company if obj.customer else None
        return empresa.tax_id if empresa else "N/A"

    @staticmethod
    def resolve_razonSocial(obj):
        cliente = obj.customer
        empresa = cliente.company if cliente else None
        return empresa.legal_name if empresa else (cliente.contact.full_name if cliente and cliente.contact else "Sin Nombre")

    @staticmethod
    def resolve_personal(obj):
        if obj.assigned_to:
            return f"{obj.assigned_to.first_name} {obj.assigned_to.last_name}".strip() or obj.assigned_to.email
        return "Sin asignar"

    @staticmethod
    def resolve_estadoId(obj):
        return obj.current_state.code if obj.current_state else None
    
# ==========================================
# SCHEMAS: TRADE (Ventas - Columna Derecha)
# ==========================================
class AttachmentOut(Schema):
    id: int
    url: str
    name: str
    
class TradeListRowOut(BaseListRowOut):
    """Esquema diseñado para la tabla/Datatable de TradeList.vue"""
    pass
    
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
    attachments: Optional[List[AttachmentOut]] = []
    
class TradeEmailDraft(Schema):
    """Para la tarjeta de Redactar Mensaje"""
    to: str
    subject: str
    body: str

class TradeMainOut(Schema):
    """El payload maestro para la vista TradeView.vue (main tag)"""
    customer_id: int
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

class ContractListRowOut(BaseListRowOut):
    """Esquema para cada fila de la tabla en ContractList"""
    pass
    
# ================================================
# SCHEMAS: BILLING (Facturación - Columna Derecha)
# ================================================

class BillingListRowOut(BaseListRowOut):
    """Esquema para cada fila de la tabla en BillingList"""
    pass
    
# ================================================
# SCHEMAS: SUPPORT (Soporte / Onboarding - Columna Derecha)
# ================================================

class SupportListRowOut(BaseListRowOut):
    """Esquema para cada fila de la tabla en SupportList"""
    pass
    
# ==========================================
# SCHEMAS: ADMINISTRATOR (Usuarios y Roles)
# ==========================================
class UserSessionInfoOut(Schema):
    ip_address: Optional[str] = None
    browser_os: Optional[str] = None

class AdminUserListOut(Schema):
    """Esquema para la tabla de directorio de usuarios en el módulo Administrador"""
    brand_user_id: int
    user_id: int
    full_name: str
    email: str
    role_name: str
    is_active: bool
    joined_at: datetime
    last_login: Optional[datetime] = None
    session_info: UserSessionInfoOut