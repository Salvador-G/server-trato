from ninja import NinjaAPI
from ninja_extra import exceptions
from ninja_jwt.routers.obtain import refresh_token 
from accounts.routers import auth_router, router as accounts_router
from accounts.routers import router as accounts_router
from core.routers import router as core_router
from customers.routers import router as customers_router
from workflows.routers import router as workflows_router
from form_engine.routers import router as form_router
from communications.routers import router as communications_router
from documents.routers import router as docs_router

from modules_api.api import modules_router
from analytics_api.api import analytics_router

# Instanciamos la API global
api = NinjaAPI(
    title="Trato API",
    version="1.0.0"
)

# Agregamos el router de Autenticación (Login)
# Esto creará los endpoints: POST /api/auth/pair (para hacer login)
api.add_router("/auth", auth_router)

api.post("/auth/refresh", tags=["Auth"])(refresh_token)

# Router de cuentas
api.add_router("/accounts", accounts_router)

# Router de core (marcas, roles, etc.)
api.add_router("/core", core_router)

# Router de customers (B2B/B2C)
api.add_router("/customers", customers_router)

# Router de workflows (procesos)
api.add_router("/workflows", workflows_router)

# Router de comunicaciones (bandejas de correo, conversaciones)
api.add_router("/communications", communications_router)

# Router de documentos (archivos subidos)
api.add_router("/documents", docs_router)

# Router de form engine (formularios dinámicos)
api.add_router("/form-engine", form_router)

# Router de módulos específicos para el frontend (BFF)
api.add_router("/modules", modules_router)

# Router de analytics (futuro módulo de análisis y reportes)
api.add_router("/analytics", analytics_router)  

# Manejador de excepciones obligatorio para ninja_jwt
@api.exception_handler(exceptions.APIException)
def api_exception_handler(request, exc):
    """
    Captura los errores de validación de JWT (ej. contraseña incorrecta)
    y los formatea correctamente para Django Ninja.
    """
    headers = {}

    if isinstance(exc.detail, (list, dict)):
        data = exc.detail
    else:
        data = {"detail": exc.detail}

    response = api.create_response(request, data, status=exc.status_code)
    for k, v in headers.items():
        response.setdefault(k, v)

    return response