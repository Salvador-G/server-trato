# core/utils/email_receiver.py
import imaplib
import email
import email.utils
from email.header import decode_header
from django.utils import timezone
from django.db import transaction
from .encryption import decrypt_password
from communications.models import EmailConfiguration, Message, Conversation
from workflows.models import WorkflowState

def get_decoded_header(header_value):
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = ""
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            result += fragment.decode(encoding or 'utf-8', errors='ignore')
        else:
            result += fragment
    return result

def extract_text_body(msg):
    """
    Extrae ÚNICAMENTE el texto del correo, ignorando logos en firmas, 
    documentos adjuntos y basura HTML pesada.
    """
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            # Ignoramos cualquier parte que sea un archivo adjunto
            if part.get('Content-Disposition') is not None:
                continue
                
            content_type = part.get_content_type()
            
            # Priorizamos texto plano por limpieza del CRM
            if content_type == "text/plain":
                body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                break # Encontramos el texto, salimos del loop para no procesar imágenes
            
            # Si no hay texto plano, intentamos rescatar el HTML
            elif content_type == "text/html" and not body:
                raw_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                # Aquí podrías usar librerías como BeautifulSoup para limpiar el HTML, 
                # pero por ahora lo guardamos en crudo.
                body = raw_html
    else:
        # Correo simple sin partes
        body = msg.get_payload(decode=True).decode('utf-8', errors='ignore')
        
    return body.strip()

def fetch_unread_emails():
    configs = EmailConfiguration.objects.filter(is_active=True)
    
    for config in configs:
        try:
            password = decrypt_password(config.imap_password)
            if config.use_ssl:
                mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
            else:
                mail = imaplib.IMAP4(config.imap_host, config.imap_port)
            
            mail.login(config.imap_username, password)
            mail.select('inbox')
            
            status, response = mail.search(None, 'UNSEEN')
            unread_msg_nums = response[0].split()
            
            for num in unread_msg_nums:
                status, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject = get_decoded_header(msg.get("Subject"))
                        raw_from = get_decoded_header(msg.get("From"))
                        
                        # === MAGIA AQUÍ: Extraemos SOLO el correo limpio ===
                        real_name, pure_email = email.utils.parseaddr(raw_from)
                        
                        print(f"\n[NUEVO CORREO] De: {pure_email} | Asunto: {subject}")

                        body = extract_text_body(msg)

                        # Buscamos usando el correo EXACTO y limpio
                        conversations = Conversation.objects.filter(
                            customer_workflow__customer__contact__email__iexact=pure_email,
                            channel='email'
                        ).order_by('-updated_at')

                        if conversations.exists():
                            Message.objects.create(
                                conversation=conversations.first(),
                                direction='inbound',
                                subject=subject,
                                body=body,
                                from_address=pure_email, # Guardamos el limpio
                                to_address=config.email_address,
                                status='delivered',
                                received_at=timezone.now()
                            )
                            print("[ÉXITO] Mensaje guardado y vinculado al CRM.")
                        else:
                            print(f"[ERROR] No hay oportunidad activa para el cliente {pure_email}.")
            mail.logout()
        except Exception as e:
            print(f"\n[ERROR CRÍTICO en {config.email_address}]: {str(e)}")
            
def fetch_unread_emails():
    configs = EmailConfiguration.objects.filter(is_active=True)
    
    for config in configs:
        try:
            password = decrypt_password(config.imap_password)
            if config.use_ssl:
                mail = imaplib.IMAP4_SSL(config.imap_host, config.imap_port)
            else:
                mail = imaplib.IMAP4(config.imap_host, config.imap_port)
            
            mail.login(config.imap_username, password)
            mail.select('inbox')
            
            status, response = mail.search(None, 'UNSEEN')
            unread_msg_nums = response[0].split()
            
            for num in unread_msg_nums:
                status, msg_data = mail.fetch(num, '(RFC822)')
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        subject = get_decoded_header(msg.get("Subject"))
                        raw_from = get_decoded_header(msg.get("From"))
                        
                        real_name, pure_email = email.utils.parseaddr(raw_from)
                        
                        print(f"\n[NUEVO CORREO] De: {pure_email} | Asunto: {subject}")

                        body = extract_text_body(msg)

                        conversations = Conversation.objects.filter(
                            customer_workflow__customer__contact__email__iexact=pure_email,
                            channel='email'
                        ).order_by('-updated_at')

                        if conversations.exists():
                            conversation = conversations.first()
                            workflow = conversation.customer_workflow
                            
                            with transaction.atomic():
                                # 1. Guardar el correo
                                Message.objects.create(
                                    conversation=conversation,
                                    direction='inbound',
                                    subject=subject,
                                    body=body,
                                    from_address=pure_email,
                                    to_address=config.email_address,
                                    status='delivered',
                                    received_at=timezone.now()
                                )
                                print(f"[ÉXITO] Mensaje guardado y vinculado al CRM para {pure_email}.")

                                # 2. Avanzar el pipeline a Negociación de forma SEGURA usando el 'code'
                                # Solo avanzamos si el workflow pertenece a Trade y está en el primer paso (lead/prospecto)
                                if workflow.workflow.code == 'trade' and workflow.current_state.code == 'lead':
                                    try:
                                        # Buscamos el estado por su CODE, no por su nombre.
                                        estado_negociacion = WorkflowState.objects.get(
                                            code='negotiation', 
                                            workflow=workflow.workflow
                                        )
                                        
                                        # Actualizamos el estado
                                        workflow.current_state = estado_negociacion
                                        workflow.save()
                                        
                                        # OPCIONAL PERO RECOMENDADO: Registrar en el historial de cambios
                                        from workflows.models import CustomerWorkflowHistory
                                        CustomerWorkflowHistory.objects.create(
                                            customer_workflow=workflow,
                                            state=estado_negociacion,
                                            user=None, # System/Auto
                                            comment="Cambiado automáticamente a Negociación tras recibir correo del cliente."
                                        )
                                        
                                        print(f"[PIPELINE] Trade {workflow.id} avanzado a Negociación automáticamente.")
                                    
                                    except WorkflowState.DoesNotExist:
                                        print(f"[ERROR CRÍTICO] No se encontró el estado con código 'negotiation' para el workflow {workflow.workflow.id}")
                        else:
                            print(f"[ERROR] No hay oportunidad activa para el cliente {pure_email}.")
            mail.logout()
        except Exception as e:
            print(f"\n[ERROR CRÍTICO en {config.email_address}]: {str(e)}")