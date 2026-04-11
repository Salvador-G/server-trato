from django.contrib import admin
from .models import Conversation, Message, MessageAttachment, EmailConfiguration

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "customer_workflow", "channel", "updated_at")
    list_filter = ("channel",)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ("id", "conversation", "direction", "subject", "status", "created_at")
    list_filter = ("direction", "status")
    search_fields = ("subject", "from_address", "to_address")

@admin.register(MessageAttachment)
class MessageAttachmentAdmin(admin.ModelAdmin):
    list_display = ("id", "message", "created_at")
    
@admin.register(EmailConfiguration)
class EmailConfigurationAdmin(admin.ModelAdmin):
    list_display = ("email_address", "brand", "smtp_host", "imap_host", "is_active")
    list_filter = ("brand", "is_active")
    search_fields = ("email_address", "brand__name")
    
    # SEGURIDAD: 
    # Hacemos que las contraseñas sean de solo lectura. 
    # El superadmin verá el hash de Fernet (gAAAAAB...), pero no podrá 
    # editarlo por error y romper la encriptación.
    readonly_fields = ("smtp_password", "imap_password", "created_at", "updated_at")

    fieldsets = (
        ("Propietario", {
            "fields": ("brand", "email_address", "is_active")
        }),
        ("Servidor de Envío (SMTP)", {
            "fields": ("smtp_host", "smtp_port", "smtp_username", "smtp_password", "use_tls")
        }),
        ("Servidor de Recepción (IMAP)", {
            "fields": ("imap_host", "imap_port", "imap_username", "imap_password", "use_ssl")
        }),
        ("Límites", {
            "fields": ("daily_send_limit", "created_at", "updated_at"),
            "classes": ("collapse",) # Lo oculta por defecto para que no estorbe
        }),
    )