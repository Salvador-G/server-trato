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
    
    # UserManager se encarga de validar el email y encriptar el password
    user = User.objects.create_user(
        email=payload.email,
        password=payload.password
    )
    
    return 201, user

# Endpoint para iniciar sesion 
@router.get("/users/me", response=UserOut)
def get_me(request):
    """Devuelve los datos del usuario autenticado actualmente"""
    # Gracias a auth=JWTAuth() en el router, request.user ya es el usuario real
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
    
    # payload.dict(exclude_unset=True) extrae SOLO lo que el cliente envió
    update_data = payload.dict(exclude_unset=True)
    
    if not update_data:
        return user # Si no enviaron nada, no hacemos hit a la BD
        
    for attr, value in update_data.items():
        setattr(user, attr, value)
        
    # Magia de rendimiento: Le decimos a Django que SOLO actualice 
    # las columnas modificadas, evitando un UPDATE masivo en SQL.
    user.save(update_fields=update_data.keys())
    
    return user

@router.delete("/users/{user_id}", response={204: None})
def delete_user(request, user_id: int):
    """Elimina un usuario de la base de datos"""
    user = get_object_or_404(User, id=user_id)
    user.delete()
    return 204, None

