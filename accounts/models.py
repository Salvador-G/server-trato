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
    
    # CAMBIO AQUÍ: Cambiamos 'upload_module' por 'upload_to'
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    def __str__(self):
        return f"Perfil de {self.user.email}"