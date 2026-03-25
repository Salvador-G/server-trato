from django.db import models
from django.conf import settings
import uuid

# =========================
# FORM
# =========================
class Form(models.Model):
    brand = models.ForeignKey(
        "core.Brand",
        on_delete=models.CASCADE,
        related_name="forms"
    )

    form_key = models.SlugField(help_text="Slug o ID público del formulario")
    
    # ¡RENOMBRADO!
    structure = models.JSONField(help_text="Estructura en JSON del formulario")
    
    version = models.PositiveIntegerField(default=1)
    description = models.CharField(max_length=255, blank=True)
    is_public = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,   
        on_delete=models.PROTECT
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("brand", "form_key", "version")
        ordering = ["-version"]
        verbose_name = "Form"
        verbose_name_plural = "Forms"

    def __str__(self):
        return f"{self.form_key} v{self.version} ({self.brand.name})"

# =========================
# FORM SUBMISSION
# =========================
class FormSubmission(models.Model):
    SOURCE_CHOICES = (
        ("widget", "Widget"),
        ("iframe", "Iframe HTML"),
        ("internal", "Internal"),
        ("api", "API"),
    )

    form = models.ForeignKey(
        Form,
        on_delete=models.CASCADE,
        related_name="submissions"
    )

    customer = models.ForeignKey(
        "customers.Customer",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="form_submissions"
    )

    submission_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    payload = models.JSONField(help_text="Respuestas enviadas en JSON")
    
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Form Submission"
        verbose_name_plural = "Form Submissions"

    def __str__(self):
        return str(self.submission_id)

# =========================
# WORKFLOW FORM
# =========================
class WorkflowForm(models.Model):
    workflow = models.ForeignKey(
        "workflows.Workflow", 
        on_delete=models.CASCADE
    )
    form = models.ForeignKey(
        Form, 
        on_delete=models.CASCADE
    )
    trigger_state = models.ForeignKey(
        "workflows.WorkflowState", 
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Estado que se dispara al llenar este formulario"
    )

    class Meta:
        unique_together = ("workflow", "form")
        verbose_name = "Workflow Form"
        verbose_name_plural = "Workflow Forms"

    def __str__(self):
        return f"{self.workflow} - {self.form}"