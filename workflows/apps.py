from django.apps import AppConfig


class WorkflowsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'workflows'
    
    def ready(self):
        """
        Este método se ejecuta cuando Django arranca.
        Aquí importamos nuestras signals para que queden registradas.
        """
        import workflows.signals