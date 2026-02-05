from django.db import models
from django.conf import settings
import uuid

# Create your models here.
class Formulario(models.Model):
    brand = models.ForeignKey(
        "core.Brand",
        on_delete=models.CASCADE,
        related_name="formularios"
    )

    form_key = models.SlugField()
    schema = models.JSONField()
    version = models.PositiveIntegerField()

    descripcion = models.CharField(max_length=255, blank=True)

    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("brand", "form_key", "version")
        ordering = ["-version"]

    def __str__(self):
        return f"{self.form_key} v{self.version}"

class FormularioEnvio(models.Model):
    formulario = models.ForeignKey(
        Formulario,
        on_delete=models.CASCADE,
        related_name="envios"
    )

    """ cliente = models.ForeignKey(
        "clientes.Cliente",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    ) """

    submission_id = models.UUIDField(default=uuid.uuid4, editable=False)

    payload = models.JSONField()

    source = models.CharField(
        max_length=20,
        choices=(
            ("widget", "Widget"),
            ("interno", "Interno"),
            ("api", "API"),
        )
    )

    submitted_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.submission_id)