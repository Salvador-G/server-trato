# core/utils/encryption.py
import base64
import hashlib
from cryptography.fernet import Fernet
from django.conf import settings

def get_fernet():
    """Deriva una llave válida de 32-bytes a partir del SECRET_KEY de Django"""
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)

def encrypt_password(plain_text: str) -> str:
    if not plain_text:
        return ""
    return get_fernet().encrypt(plain_text.encode()).decode()

def decrypt_password(cipher_text: str) -> str:
    if not cipher_text:
        return ""
    try:
        return get_fernet().decrypt(cipher_text.encode()).decode()
    except Exception:
        return ""