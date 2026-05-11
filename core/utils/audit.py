# core/utils/audit.py
from core.models import AuditLog
from core.utils.network import get_client_ip # Importamos la utilidad de red

def log_audit_event(request, action, actor=None, brand=None, details=None):
    """
    Helper estandarizado para registrar eventos de auditoría.
    """
    ip = get_client_ip(request)
    ua = request.META.get('HTTP_USER_AGENT', '')[:255]

    AuditLog.objects.create(
        brand=brand,
        actor=actor,
        action=action,
        details=details or {},
        ip_address=ip,
        user_agent=ua
    )