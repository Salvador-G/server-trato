# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import User, UserProfile # Añadimos UserProfile

# 1. Adaptamos los formularios nativos a tu modelo basado en Email
class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email', 'first_name', 'last_name') # Ahora también pedimos nombres al crear un usuario

# NUEVO: Creamos un "Inline" para que el Perfil se edite dentro del Usuario
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Perfil Adicional (Datos Legales y Contacto)'

# 2. Creamos el Admin personalizado
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Enlazamos los formularios
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    # ACTUALIZADO: Añadimos first_name y last_name a la tabla principal
    list_display = ('email', 'first_name', 'last_name', 'is_staff', 'is_active', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('email', 'first_name', 'last_name') # Ahora puedes buscar por nombre
    ordering = ('email',)

    # Conectamos el Perfil al final de la página del usuario
    inlines = (UserProfileInline,)

    # 3. Reescribimos los fieldsets para incluir "Nombres" y "Apellidos"
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Información Personal', {'fields': ('first_name', 'last_name')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas Importantes', {'fields': ('last_login',)}),
    )

    # Cómo se ve la pantalla al darle "Añadir Usuario" en el Admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            # Opcional: También podemos pedirlos al momento de crear el usuario
            'fields': ('email', 'password1', 'password2', 'first_name', 'last_name'), 
        }),
    )