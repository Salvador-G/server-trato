import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase  # <-- NUEVO
from email import encoders  # <-- NUEVO
from .encryption import decrypt_password


# 1. AÑADIMOS "attachments=None" A LA FIRMA
def send_dynamic_email(
    email_config,
    to_address: str,
    subject: str,
    body: str,
    from_header: str,
    attachments=None,
):
    """
    Se conecta al SMTP del cliente, desencripta su contraseña y envía el correo real con adjuntos.
    Devuelve (True, None) si fue exitoso, o (False, error_msg) si falló.
    """
    # 1. Armamos el paquete del correo
    msg = MIMEMultipart()
    msg["From"] = from_header
    msg["To"] = to_address
    msg["Subject"] = subject or "Sin Asunto"
    msg.attach(
        MIMEText(body, "plain")
    )  # Si usas un editor rico en el frontend, cambia 'plain'  por 'html'

    # ==========================================
    # NUEVO: PROCESAMIENTO DE ADJUNTOS
    # ==========================================
    if attachments:
        for att in attachments:
            filepath = att["filepath"]
            filename = att["filename"]

            # Validamos que el archivo físico exista en el servidor
            if os.path.exists(filepath):
                # Leemos el archivo en formato binario ('rb')
                with open(filepath, "rb") as f:
                    file_content = f.read()

                # Creamos un paquete MIME de tipo genérico (octet-stream)
                part = MIMEBase("application", "octet-stream")
                part.set_payload(file_content)

                # Codificamos el archivo a Base64 para que sea seguro enviarlo por SMTP
                encoders.encode_base64(part)

                # Añadimos los encabezados para que Gmail/Outlook sepan que es un archivo adjunto y su nombre
                part.add_header(
                    "Content-Disposition", f'attachment; filename="{filename}"'
                )

                # Lo metemos en el sobre del correo
                msg.attach(part)
            else:
                print(
                    f"Advertencia: Archivo adjunto no encontrado en la ruta: {filepath}"
                )

    # 2. Desencriptamos la contraseña
    plain_password = decrypt_password(email_config.smtp_password)

    # 3. Nos conectamos y enviamos
    try:
        if email_config.smtp_port == 465:
            # El puerto 465 requiere conexión segura inmediata (SMTP_SSL)
            server = smtplib.SMTP_SSL(email_config.smtp_host, email_config.smtp_port)
        else:
            # El puerto 587 u otros usan conexión normal y luego starttls()
            server = smtplib.SMTP(email_config.smtp_host, email_config.smtp_port)
            if email_config.use_tls:
                server.starttls()

        # Iniciamos sesión y disparamos
        server.login(email_config.smtp_username, plain_password)
        server.send_message(msg)
        server.quit()

        return True, None
    except Exception as e:
        # Capturamos si la contraseña está mal, si el puerto está bloqueado, etc.
        return False, str(e)
