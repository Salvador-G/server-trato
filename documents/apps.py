# documents/apps.py
from django.apps import AppConfig

class DocumentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'documents'

    def ready(self):
        # IMPORTANTE: Esto asegura que la señal escuche en producción
        import documents.signals