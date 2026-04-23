from ninja import ModelSchema, Schema
from typing import Optional
from django.contrib.auth import get_user_model

User = get_user_model()

class UserOut(ModelSchema):
    """Esquema de SALIDA: Lo que la API devuelve (NUNCA expone el password)"""
    class Meta:
        model = User
        fields = [
            'id', 
            'email', 
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
    document_id: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None