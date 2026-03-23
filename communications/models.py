# communications/models.py
from django.db import models

# =========================
# EMAIL CONFIGURATION (BYOE)
# =========================
class EmailConfiguration(models.Model):
    brand = models.ForeignKey(
        "core.Brand", 
        on_delete=models.CASCADE, 
        related_name="email_configs"
    )
    email_address = models.EmailField(verbose_name="Dirección de Correo (Ej: ventas@marca.com)")
    
    # --- DATOS SMTP (Envío) ---
    smtp_host = models.CharField(max_length=255, verbose_name="Host SMTP")
    smtp_port = models.IntegerField(default=587, verbose_name="Puerto SMTP")
    smtp_username = models.CharField(max_length=255, verbose_name="Usuario SMTP")
    smtp_password = models.CharField(max_length=500, verbose_name="Contraseña SMTP (Encriptada)")
    use_tls = models.BooleanField(default=True)

    # --- DATOS IMAP (Recepción) ---
    imap_host = models.CharField(max_length=255, verbose_name="Host IMAP")
    imap_port = models.IntegerField(default=993, verbose_name="Puerto IMAP")
    imap_username = models.CharField(max_length=255, verbose_name="Usuario IMAP")
    imap_password = models.CharField(max_length=500, verbose_name="Contraseña IMAP (Encriptada)")
    use_ssl = models.BooleanField(default=True)

    # --- SEGURIDAD ---
    daily_send_limit = models.IntegerField(default=100)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Email Configuration"
        verbose_name_plural = "Email Configurations"
        unique_together = ("brand", "email_address")

    def __str__(self):
        return f"{self.email_address} ({self.brand.name})"


# =========================
# CONVERSATION (El hilo o "Ticket")
# =========================
class Conversation(models.Model):
    CHANNEL_CHOICES = (
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'), 
        ('sms', 'SMS'),
    )

    customer_workflow = models.ForeignKey(
        "workflows.CustomerWorkflow", 
        on_delete=models.CASCADE, 
        related_name="conversations",
        verbose_name="Proceso del Cliente"
    )
    
    channel = models.CharField(
        max_length=20, 
        choices=CHANNEL_CHOICES, 
        default='email',
        verbose_name="Canal de Comunicación"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"Conversación #{self.id} ({self.get_channel_display()}) - {self.customer_workflow}"

# =========================
# MESSAGE (El mensaje Omnicanal)
# =========================
class Message(models.Model):
    DIRECTION_CHOICES = (
        ('inbound', 'Entrante (Del cliente)'),
        ('outbound', 'Saliente (Hacia el cliente)'),
    )
    
    STATUS_CHOICES = (
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
        ('delivered', 'Entregado'),
        ('read', 'Leído'),
        ('error', 'Error de envío'),
    )

    conversation = models.ForeignKey(
        Conversation, 
        on_delete=models.CASCADE, 
        related_name="messages",
        verbose_name="Hilo de Conversación"
    )
    
    direction = models.CharField(max_length=15, choices=DIRECTION_CHOICES, verbose_name="Dirección")
    subject = models.CharField(max_length=255, blank=True, null=True, verbose_name="Asunto")
    body = models.TextField(verbose_name="Cuerpo del mensaje")
    
    from_address = models.CharField(max_length=255, verbose_name="De (Remitente / Teléfono)")
    to_address = models.CharField(max_length=255, verbose_name="Para (Destinatario / Teléfono)")
    
    provider_message_id = models.CharField(max_length=255, blank=True, verbose_name="ID del Proveedor (SendGrid/Meta)")
    in_reply_to = models.CharField(max_length=255, blank=True, verbose_name="En respuesta a (ID)")
    
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='draft', verbose_name="Estado")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadata Omnicanal")
    
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name="Enviado el")
    received_at = models.DateTimeField(null=True, blank=True, verbose_name="Recibido el")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.get_direction_display()} - {self.subject or 'Sin Asunto'} ({self.status})"

# =========================
# MESSAGE ATTACHMENT (Adjuntos)
# =========================
class MessageAttachment(models.Model):
    message = models.ForeignKey(
        Message, 
        on_delete=models.CASCADE, 
        related_name="attachments",
        verbose_name="Mensaje"
    )
    
    file = models.FileField(
        upload_to="attachments/%Y/%m/", 
        verbose_name="Archivo Adjunto"
    )
    
    mime_type = models.CharField(max_length=100, blank=True, verbose_name="MIME Type")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Message Attachment"
        verbose_name_plural = "Message Attachments"

    def __str__(self):
        return self.file.name.split('/')[-1] if self.file else "Adjunto vacío"