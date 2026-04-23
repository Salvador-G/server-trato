# Models

```python
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    BaseUserManager,
)

# =========================
# USER MANAGER
# =========================
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("El usuario debe tener un correo electrónico (email).")

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("El superusuario debe tener is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("El superusuario debe tener is_superuser=True.")

        return self.create_user(email, password, **extra_fields)

# =========================
# USER MODEL (Identidad Global)
# =========================
class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, verbose_name="Email Address")
    
    first_name = models.CharField(max_length=150, blank=True, verbose_name="Nombres")
    last_name = models.CharField(max_length=150, blank=True, verbose_name="Apellidos")

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False) # Requerido para entrar al panel admin de Django

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email
    
# =========================
# USER PROFILE
# =========================
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    document_id = models.CharField(max_length=20, blank=True, verbose_name="DNI / CE")
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return f"Perfil de {self.user.email}"
```

# Schemas

```python
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
```

# Routes

```python
from ninja import Router
from typing import List
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from ninja_jwt.authentication import JWTAuth
from .schemas import UserOut, UserCreate, UserUpdate

User = get_user_model()
router = Router(tags=["Accounts"], auth=JWTAuth())

@router.post("/users", response={201: UserOut})
def create_user(request, payload: UserCreate):
    """Crea un nuevo usuario usando el UserManager personalizado"""
    
    user = User.objects.create_user(
        email=payload.email,
        password=payload.password
    )
    
    return 201, user


# Endpoint para iniciar sesion 
@router.get("/users/me", response=UserOut)
def get_me(request):
    """Devuelve los datos del usuario autenticado actualmente"""
    return request.user


@router.get("/users", response=List[UserOut])
def list_users(request):
    """Lista todos los usuarios registrados"""
    return User.objects.all()


@router.get("/users/{user_id}", response=UserOut)
def get_user(request, user_id: int):
    """Obtiene un usuario por su ID"""
    user = get_object_or_404(User, id=user_id)
    return user


@router.patch("/users/{user_id}", response=UserOut)
def partial_update_user(request, user_id: int, payload: UserUpdate):
    """Actualización parcial (PATCH) optimizada para rendimiento"""
    user = get_object_or_404(User, id=user_id)
    
    update_data = payload.dict(exclude_unset=True)
    
    if not update_data:
        return user
        
    for attr, value in update_data.items():
        setattr(user, attr, value)
        
    user.save(update_fields=update_data.keys())
    
    return user


@router.delete("/users/{user_id}", response={204: None})
def delete_user(request, user_id: int):
    """Elimina un usuario de la base de datos"""
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return 204, None
```