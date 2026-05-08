    # communications/schemas.py
from ninja import ModelSchema, Schema
from typing import List, Optional
from .models import EmailConfiguration, Conversation, Message, MessageAttachment

# =========================
# EMAIL CONFIGURATION (BYOE)
# =========================
class EmailConfigOut(ModelSchema):
    # Omitimos las contraseñas en la salida por seguridad
    class Meta:
        model = EmailConfiguration
        fields = [
            'id', 'email_address', 'smtp_host', 'smtp_port', 'smtp_username', 'use_tls',
            'imap_host', 'imap_port', 'imap_username', 'use_ssl', 'is_active'
        ]

class EmailConfigCreate(Schema):
    email_address: str
    smtp_host: str
    smtp_port: int = 587
    smtp_username: str
    smtp_password: str # En texto plano (lo encriptaremos en el router)
    use_tls: bool = True
    imap_host: str
    imap_port: int = 993
    imap_username: str
    imap_password: str # En texto plano
    use_ssl: bool = True

# =========================
# CONVERSACIONES Y MENSAJES
# =========================
class MessageAttachmentOut(ModelSchema):
    file_url: Optional[str] = None
    mime_type: Optional[str] = None
    name: Optional[str] = None

    class Meta:
        model = MessageAttachment
        # Quitamos mime_type de aquí porque ahora vive en Document
        fields = ['id', 'created_at'] 

    @staticmethod
    def resolve_file_url(obj: MessageAttachment) -> Optional[str]:
        # Viajamos a través de la relación para obtener la URL
        return obj.document.file.url if obj.document and obj.document.file else None
        
    @staticmethod
    def resolve_mime_type(obj: MessageAttachment) -> Optional[str]:
        return obj.document.mime_type if obj.document else None
        
    @staticmethod
    def resolve_name(obj: MessageAttachment) -> Optional[str]:
        return obj.document.original_filename if obj.document else "Documento_Adjunto"

class MessageOut(ModelSchema):
    attachments: List[MessageAttachmentOut] = []
    class Meta:
        model = Message
        fields = [
            'id', 'direction', 'subject', 'body', 'from_address', 
            'to_address', 'status', 'sent_at', 'created_at'
        ]

class ConversationOut(ModelSchema):
    customer_workflow_id: int
    class Meta:
        model = Conversation
        fields = ['id', 'channel', 'created_at', 'updated_at']

class SendMessagePayload(Schema):
    customer_workflow_id: int
    channel: str # 'email', 'whatsapp', 'sms'
    body: str
    subject: Optional[str] = None
    to_address: str
    advance_state_to: Optional[str] = None
    document_ids : Optional[List[int]] = []