from ninja import ModelSchema
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
    """Esquema para actualizar datos de un usuario existente"""
    class Meta:
        model = User
        fields = ['is_active', 'is_staff', 'is_superuser']
        config = {
            "extra": "ignore" # Ignora campos extra si el frontend los envía por error
        }