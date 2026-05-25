from ninja import Router

from .routers.trade import router as trade_router
#from .routers.contract import router as contract_router

analytics_router = Router()
analytics_router.add_router("/trade", trade_router)
#analytics_router.add_router("/contract", contract_router)