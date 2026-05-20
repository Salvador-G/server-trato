from ninja import ModelSchema, Schema
from typing import Optional
from django.contrib.auth import get_user_model
from .models import UserProfile

User = get_user_model()

class UserProfileOut(ModelSchema):
    class Meta:
        model = UserProfile
        fields = ['document_type', 'document_id', 'phone', 'address', 'avatar']

class UserMeUpdate(Schema):
    """Payload para actualizar el perfil propio (mezcla datos de User y UserProfile)"""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    document_type: Optional[str] = None
    document_id: Optional[str] = None
    address: Optional[str] = None

class ChangePasswordInput(Schema):
    """Payload para cambio de clave de seguridad"""
    current_password: str
    new_password: str
    
class UserOut(ModelSchema):
    """Esquema de SALIDA: Lo que la API devuelve (NUNCA expone el password)"""
    
    profile: Optional[UserProfileOut] = None
    
    class Meta:
        model = User
        fields = [
            'id', 
            'email',
            'first_name',
            'last_name',
            'is_active', 
            'is_staff', 
            'is_superuser', 
            'created_at', 
            'updated_at'
        ]

class UserCreate(ModelSchema):
    """Esquema de ENTRADA: Lo que se recibe para crear un usuario"""
    class Meta:
        model = User
        fields = ['email', 'password']
        
class UserUpdate(ModelSchema):
    """Esquema de usuario normal: Solo puede editar su propia info básica"""
    class Meta:
        model = User
        fields = ['first_name', 'last_name']
        config = { "extra": "ignore" }

class AdminUserUpdate(ModelSchema):
    """Esquema para Superadmins: Permite escalar privilegios y accesos"""
    class Meta:
        model = User
        fields = ['is_active', 'is_staff', 'is_superuser']
        config = { "extra": "ignore" }
        


class EmployeeCreateInput(Schema):
    """Payload que envía el Admin de la marca para crear un empleado"""
    # Obligatorios
    email: str
    password: str
    first_name: str
    last_name: str
    role_id: int  # <-- Crucial para la tabla BrandUser
    
    # Opcionales (Perfil legal/operativo)
    document_type: Optional[str] = None
    document_id: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None