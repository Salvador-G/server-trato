# documents/models.py
import os
import uuid
import hashlib
import logging
import magic
from PIL import Image
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

# =========================
# CONFIGURACIÓN DE SEGURIDAD
# =========================
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'xlsx', 'jpg', 'jpeg', 'png', 'txt'}
MAX_UPLOAD_SIZE = 15 * 1024 * 1024  # 15 MB

# Whitelist de MIME types reales (Evita MIME Spoofing)
ALLOWED_MIMES = {
    'application/pdf': 'pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
    'image/jpeg': 'jpg', 
    'image/png': 'png',
    'text/plain': 'txt'
}

def validate_file_size(file):
    if file.size > MAX_UPLOAD_SIZE:
        raise ValidationError(f"El archivo excede el límite de {MAX_UPLOAD_SIZE / (1024*1024)} MB.")

# =========================
# Función segura para renombrar y organizar archivos
# =========================
def document_upload_path(instance, filename):
    # CRÍTICO 1: Sanitización estricta de extensión
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError(f"Extensión .{ext} no permitida.")
    
    if instance.customer.customer_type == 'B2B' and instance.customer.company:
        raw_name = instance.customer.company.legal_name
    elif instance.customer.customer_type == 'B2C' and instance.customer.contact:
        raw_name = instance.customer.contact.full_name
    else:
        raw_name = f"cliente_{instance.customer.id}"

    clean_name = slugify(raw_name.replace("&", "y")).replace("-", "_")[:200]
    current_time = timezone.now().strftime("%Y%m%d")
    
    # IMPORTANTE 6: UUID de 16 caracteres para evitar colisiones
    unique_id = uuid.uuid4().hex[:16] 
    
    new_filename = f"{clean_name}_{current_time}_{unique_id}.{ext}"
    brand_folder = f"marca_{instance.brand.id}"
    
    raw_doc_type = instance.document_type.code if instance.document_type else 'otros'
    doc_type = slugify(raw_doc_type)
    
    return os.path.join("documentos", brand_folder, doc_type, new_filename)

# =========================
# DOCUMENT TYPE
# =========================
class DocumentType(models.Model):
    brand = models.ForeignKey("core.Brand", on_delete=models.CASCADE, related_name="document_types")
    code = models.CharField(max_length=50, verbose_name="Código")
    name = models.CharField(max_length=100, verbose_name="Nombre del Tipo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Document Type"
        verbose_name_plural = "Document Types"
        ordering = ["name"]
        unique_together = ("brand", "code")

    def __str__(self):
        return self.name

# =========================
# DOCUMENT (El archivo final)
# =========================
class Document(models.Model):
    brand = models.ForeignKey("core.Brand", on_delete=models.CASCADE, related_name="documents")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="documents")
    document_type = models.ForeignKey(DocumentType, on_delete=models.RESTRICT)
    workflow = models.ForeignKey("workflows.Workflow", on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey("workflows.WorkflowState", on_delete=models.SET_NULL, null=True, blank=True)

    file = models.FileField(
        upload_to=document_upload_path, 
        validators=[validate_file_size], # Quitamos FileExtensionValidator nativo porque ya lo hacemos manual más seguro
        verbose_name="Archivo Físico"
    )
    
    original_filename = models.CharField(max_length=255, blank=True)
    file_size = models.PositiveIntegerField(null=True, blank=True)
    checksum = models.CharField(max_length=64, blank=True, db_index=True)
    mime_type = models.CharField(max_length=100, blank=True)
    
    metadata = models.JSONField(default=dict, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Document"
        verbose_name_plural = "Documents"
        ordering = ["-created_at"]
        
        # CRÍTICO 2: Race Condition resuelta a nivel Base de Datos
        constraints = [
            models.UniqueConstraint(
                fields=['brand', 'checksum'],
                name='unique_brand_checksum'
            )
        ]
        
        indexes = [
            models.Index(fields=['brand', 'customer', '-created_at']),
            models.Index(fields=['brand', 'document_type']),
            models.Index(fields=['brand', 'checksum']), # RENDIMIENTO 9: Índice compuesto
        ]

    def __str__(self):
        return f"{self.document_type.name} - {self.original_filename}"

    def clean(self):
        super().clean()
        
        # 1. Validación Multi-Tenant
        if getattr(self, 'document_type_id', None) and getattr(self, 'brand_id', None):
            if self.document_type.brand_id != self.brand_id:
                raise ValidationError({"document_type": "El tipo de documento no pertenece a esta marca."})

        # 2. Validación de Orfandad Workflow/State
        if getattr(self, 'state_id', None) and getattr(self, 'workflow_id', None):
            if self.state.workflow_id != self.workflow_id:
                raise ValidationError({"state": "El estado no pertenece al proceso (workflow) seleccionado."})

        # === ESCÁNER DE SEGURIDAD EN MEMORIA (ANTES DE GUARDAR EN DISCO) ===
        if self.file and (not self.pk or hasattr(self.file.file, 'read')):
            try:
                # A. Leemos solo los primeros 2KB para el MIME
                header = self.file.read(2048)
                real_mime = magic.from_buffer(header, mime=True)

                # B. Bloquear MIME spoofing y loguear el intento de ataque
                if real_mime not in ALLOWED_MIMES:
                    ext = os.path.splitext(self.file.name)[1].lower()
                    logger.warning(
                        f"SECURITY: Intento de upload malicioso bloqueado | "
                        f"MIME real: {real_mime} | Extensión falsa: {ext}"
                    )
                    raise ValidationError(f"Tipo de archivo detectado no permitido: {real_mime}")

                self.mime_type = real_mime

                # C. Validación de imágenes corruptas o inyectadas con código
                if real_mime.startswith('image/'):
                    self.file.seek(0)
                    try:
                        img = Image.open(self.file)
                        img.verify()
                    except Exception as e:
                        logger.error(f"Imagen corrupta detectada: {e}")
                        raise ValidationError("Archivo de imagen inválido o corrupto.")

                # D. Cálculo de Hash optimizado en un solo pase (Aprovechamos el header ya leído)
                hasher = hashlib.sha256()
                hasher.update(header)
                self.file.seek(2048)
                for chunk in self.file.chunks(chunk_size=8192):
                    hasher.update(chunk)

                self.checksum = hasher.hexdigest()
                self.file.seek(0) # Reseteamos el puntero para que Django lo guarde bien luego
                
                # E. Check de duplicados con el hash recién calculado
                if Document.objects.filter(brand=self.brand, checksum=self.checksum).exists():
                    raise ValidationError("Este documento ya fue subido previamente para esta marca.")

            except ValidationError:
                raise
            except Exception as e:
                logger.error(f"Error en escáner de memoria: {e}")
                raise ValidationError(f"Error al analizar el archivo: {str(e)}")

    def save(self, *args, **kwargs):
        # Como todo el trabajo duro se hizo en clean(), save() queda super ligero
        if self.file and not self.original_filename:
            self.original_filename = self.file.name
            self.file_size = self.file.size
            
        # Ejecutamos clean para garantizar el escaneo
        self.clean()
        super().save(*args, **kwargs)


# =========================
# SIGNALS (Manejo Seguro de Eliminación)
# =========================
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver

@receiver(post_delete, sender=Document)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    if instance.file:
        # RENDIMIENTO 8: Función segura para evitar que fallos de S3 rompan la transacción
        def safe_delete():
            try:
                instance.file.delete(save=False)
            except Exception as e:
                logger.error(f"Error eliminando archivo físico {instance.file.name}: {e}")
                
        transaction.on_commit(safe_delete)

@receiver(pre_save, sender=Document)
def auto_delete_file_on_change(sender, instance, **kwargs):
    if not instance.pk:
        return False

    # SEGURIDAD 4: Validación multi-tenant al buscar el archivo viejo
    old_doc = Document.objects.filter(pk=instance.pk, brand=instance.brand).first()
    if not old_doc:
        return False

    new_file = instance.file
    if old_doc.file and not old_doc.file == new_file:
        def safe_delete_old():
            try:
                old_doc.file.delete(save=False)
            except Exception as e:
                logger.error(f"Error eliminando archivo antiguo {old_doc.file.name}: {e}")
                
        transaction.on_commit(safe_delete_old)