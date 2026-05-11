# core/utils/network.py
from django.core.cache import cache
from ninja.errors import HttpError
from functools import wraps

def get_client_ip(request):
    """Extrae la IP real del cliente superando proxies reversos."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip

def rate_limit(max_requests=5, window_seconds=60):
    """
    Bloquea la IP si excede el número máximo de peticiones en la ventana de tiempo.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            ip = get_client_ip(request)
            # Clave única en caché: ej. "ratelimit_190.23.45.67_custom_login"
            cache_key = f"ratelimit_{ip}_{func.__name__}"
            
            # Consultamos cuántos intentos van
            intentos = cache.get(cache_key, 0)
            
            if intentos >= max_requests:
                # Código 429 = Too Many Requests
                raise HttpError(429, "Demasiados intentos. Por favor, espera 1 minuto.")
            
            # Si es el primer intento, creamos la llave con su tiempo de expiración
            if intentos == 0:
                cache.set(cache_key, 1, timeout=window_seconds)
            else:
                # Incrementamos el contador
                cache.incr(cache_key)
                
            return func(request, *args, **kwargs)
        return wrapper
    return decorator