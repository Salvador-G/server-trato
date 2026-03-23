# accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import User

# 1. Adaptamos los formularios nativos a tu modelo basado en Email
class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User

class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('email',)

# 2. Creamos el Admin personalizado
@admin.register(User)
class CustomUserAdmin(UserAdmin):
    # Enlazamos los formularios
    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    # Configuramos qué columnas se ven en la lista
    list_display = ('email', 'is_staff', 'is_active', 'is_superuser')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
    search_fields = ('email',)
    ordering = ('email',)

    # 3. Reescribimos los fieldsets porque ya no tenemos 'username' ni 'nombres'
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Permisos', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Fechas Importantes', {'fields': ('last_login',)}), # created_at y updated_at son automáticos, no van aquí
    )

    # Cómo se ve la pantalla al darle "Añadir Usuario" en el Admin
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password'), # CustomUserCreationForm pedirá la contraseña dos veces para confirmar
        }),
    )