# core/utils/email_sender.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .encryption import decrypt_password

def send_dynamic_email(email_config, to_address: str, subject: str, body: str, from_header: str):
    """
    Se conecta al SMTP del cliente, desencripta su contraseña y envía el correo real.
    Devuelve (True, None) si fue exitoso, o (False, error_msg) si falló.
    """
    # 1. Armamos el paquete del correo
    msg = MIMEMultipart()
    msg['From'] = from_header
    msg['To'] = to_address
    msg['Subject'] = subject or "Sin Asunto"
    msg.attach(MIMEText(body, 'plain')) # Si usas un editor rico en el frontend, cambia 'plain' por 'html'

    # 2. Desencriptamos la contraseña
    plain_password = decrypt_password(email_config.smtp_password)

    # 3. Nos conectamos y enviamos
    try:
        server = smtplib.SMTP(email_config.smtp_host, email_config.smtp_port)
        
        if email_config.use_tls:
            server.starttls() # Aseguramos la conexión
            
        server.login(email_config.smtp_username, plain_password)
        server.send_message(msg)
        server.quit()
        
        return True, None
    except Exception as e:
        # Capturamos si la contraseña está mal, si el puerto está bloqueado, etc.
        return False, str(e)