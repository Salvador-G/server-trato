from django.urls import path
from .views import (
    FormularioCreateAPIView,
    FormularioListAPIView,
    FormularioPublicAPIView,
    FormularioSubmitAPIView,
)

app_name = "form_engine"

urlpatterns = [
    # Privadas (backend / builder)
    path(
        "formularios/",
        FormularioListAPIView.as_view(),
        name="formulario-list",
    ),
    path(
        "formularios/create/",
        FormularioCreateAPIView.as_view(),
        name="formulario-create",
    ),

    # Públicas (widget)
    path(
        "public/<slug:brand_slug>/<slug:form_key>/",
        FormularioPublicAPIView.as_view(),
        name="formulario-public",
    ),
    path(
        "public/<slug:brand_slug>/<slug:form_key>/submit/",
        FormularioSubmitAPIView.as_view(),
        name="formulario-submit",
    ),
]
