# core/utils/email_receiver.py
import imaplib
import email
import email.utils
import os
import uuid
import hashlib
from email.header import decode_header
from django.utils import timezone
from django.db import transaction
from django.core.files.base import ContentFile
from .encryption import decrypt_password
from communications.models import (
    EmailConfiguration,
    Message,
    Conversation,
    MessageAttachment,
)
from workflows.models import WorkflowState
from documents.models import Document, DocumentType


def get_decoded_header(header_value):
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = ""
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            result += fragment.decode(encoding or "utf-8", errors="ignore")
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
            if part.get("Content-Disposition") is not None:
                continue

            content_type = part.get_content_type()

            # Priorizamos texto plano por limpieza del CRM
            if content_type == "text/plain":
                body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                break  # Encontramos el texto, salimos del loop

            # Si no hay texto plano, intentamos rescatar el HTML
            elif content_type == "text/html" and not body:
                raw_html = part.get_payload(decode=True).decode(
                    "utf-8", errors="ignore"
                )
                body = raw_html
    else:
        # Correo simple sin partes
        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

    return body.strip()


def save_email_attachments(msg, message_obj, customer, tenant):
    print(f"\n--- 🔍 BUSCANDO ADJUNTOS EN: {message_obj.subject} ---")
    doc_type, _ = DocumentType.objects.get_or_create(
        brand=tenant,
        code='adjunto_correo',
        defaults={'name': 'Adjunto de Correo'}
    )

    for part in msg.walk():
        content_type = part.get_content_type()
        print(f"[*] Analizando pieza del correo tipo: {content_type}")
        
        if part.get_content_maintype() == 'multipart':
            continue

        filename = part.get_filename()
        content_disposition = str(part.get("Content-Disposition") or "")
        
        print(f"    - Nombre detectado: {filename}")
        print(f"    - Disposition: {content_disposition}")

        # Si tiene nombre O dice explícitamente ser un adjunto
        if filename or "attachment" in content_disposition:
            if not filename:
                filename = f"adjunto_{uuid.uuid4().hex[:8]}.bin"
            else:
                filename = get_decoded_header(filename)
            
            payload = part.get_payload(decode=True)
            if not payload:
                print("    [X] Error: El contenido del archivo está vacío.")
                continue

            print(f"    -> Intentando guardar: {filename} ({len(payload)} bytes)")
            
            file_data = ContentFile(payload, name=filename)
            
            try:
                with transaction.atomic():
                    # 1. Calculamos el hash antes de intentar crear nada
                    hasher = hashlib.sha256()
                    hasher.update(payload)
                    file_checksum = hasher.hexdigest()

                    # 2. Buscamos si ya existe este archivo en la marca
                    new_doc = Document.objects.filter(brand=tenant, checksum=file_checksum).first()

                    if not new_doc:
                        # Si no existe, lo creamos normalmente
                        new_doc = Document(
                            brand=tenant,
                            customer=customer,
                            document_type=doc_type,
                            created_by=None
                        )
                        new_doc.file = file_data
                        new_doc.full_clean()
                        new_doc.save()
                        print(f"    [NUEVO] Archivo {filename} creado.")
                    else:
                        print(f"    [REUTILIZADO] El archivo {filename} ya existía, vinculando registro...")

                    # 3. Vinculamos (sea nuevo o existente) al mensaje
                    MessageAttachment.objects.create(
                        message=message_obj,
                        document=new_doc
                    )
                    print(f"    [ÉXITO] Archivo {filename} indexado correctamente.")

            except Exception as e:
                print(f"    [ERROR] {str(e)}")
    print("---------------------------------------------------\n")


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
            mail.select("inbox")

            status, response = mail.search(None, "UNSEEN")
            unread_msg_nums = response[0].split()

            for num in unread_msg_nums:
                status, msg_data = mail.fetch(num, "(RFC822)")
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])

                        subject = get_decoded_header(msg.get("Subject"))
                        raw_from = get_decoded_header(msg.get("From"))

                        real_name, pure_email = email.utils.parseaddr(raw_from)
                        print(f"\n[NUEVO CORREO] De: {pure_email} | Asunto: {subject}")

                        body = extract_text_body(msg)

                        # Buscamos SOLO en procesos que NO hayan terminado
                        conversations = Conversation.objects.filter(
                            customer_workflow__customer__contact__email__iexact=pure_email,
                            channel="email",
                            customer_workflow__finished_at__isnull=True,
                        ).order_by("-updated_at")

                        if conversations.exists():
                            conversation = conversations.first()
                            workflow = conversation.customer_workflow

                            with transaction.atomic():
                                # 1. Guardar el correo
                                new_msg = Message.objects.create(
                                    conversation=conversation,
                                    direction="inbound",
                                    subject=subject,
                                    body=body,
                                    from_address=pure_email,
                                    to_address=config.email_address,
                                    status="delivered",
                                    received_at=timezone.now(),
                                )

                                # 2. Extraer y guardar los archivos adjuntos
                                save_email_attachments(
                                    msg, new_msg, workflow.customer, config.brand
                                )

                                # 3. Actualizar la conversación para que suba de prioridad
                                conversation.updated_at = timezone.now()
                                conversation.save()

                                print(
                                    f"[ÉXITO] Mensaje guardado y vinculado al CRM para {pure_email}."
                                )

                                # 4. Avanzar el pipeline a Negociación de forma SEGURA
                                if (
                                    workflow.workflow.code == "trade"
                                    and workflow.current_state.code == "lead"
                                ):
                                    try:
                                        estado_negociacion = WorkflowState.objects.get(
                                            code="negotiation",
                                            workflow=workflow.workflow,
                                        )

                                        workflow.current_state = estado_negociacion
                                        workflow.save()

                                        from workflows.models import (
                                            CustomerWorkflowHistory,
                                        )

                                        CustomerWorkflowHistory.objects.create(
                                            customer_workflow=workflow,
                                            state=estado_negociacion,
                                            user=None,
                                            comment="Cambiado a Negociación tras recibir correo del cliente.",
                                        )
                                        print(
                                            f"[PIPELINE] Trade {workflow.id} avanzado a Negociación."
                                        )
                                    except WorkflowState.DoesNotExist:
                                        print(
                                            f"[ERROR] Estado 'negotiation' no encontrado."
                                        )
                        else:
                            print(
                                f"[IGNORADO] No hay Tratos/Procesos ACTIVOS para el cliente {pure_email}."
                            )
            mail.logout()
        except Exception as e:
            print(f"\n[ERROR CRÍTICO en {config.email_address}]: {str(e)}")
