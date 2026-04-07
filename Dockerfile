# Etapa base: Usar una imagen oficial y ligera de Python
FROM python:3.11-slim

# Variables de entorno para optimizar Python en contenedores
# Evita que Python escriba archivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
# Evita que Python almacene en buffer el stdout/stderr (útil para ver logs en tiempo real en Dokploy)
ENV PYTHONUNBUFFERED 1

# Establecer el directorio de trabajo
WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar paquetes (como psycopg2 para PostgreSQL)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar solo el archivo de requerimientos primero (aprovecha la caché de Docker)
COPY requirements.txt .

# Instalar las dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del código del proyecto
COPY . .

# Exponer el puerto en el que correrá Gunicorn
EXPOSE 8000

# Comando para ejecutar la aplicación (Asegúrate de cambiar "tu_proyecto" por el nombre de la carpeta donde está tu asgi.py)
CMD ["gunicorn", "config.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]