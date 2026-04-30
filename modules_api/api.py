# modules_api/api.py
from ninja import Router

# Importamos los submódulos (routers específicos)
from .routers.shared import router as shared_router
from .routers.trade import router as trade_router
from .routers.contract import router as contract_router
from .routers.billing import router as billing_router

# Creamos un router principal para agrupar todas las fachadas
modules_router = Router()

# Anidamos los submódulos
modules_router.add_router("/shared", shared_router)
modules_router.add_router("/trade", trade_router)
modules_router.add_router("/contract", contract_router)
modules_router.add_router("/billing", billing_router)