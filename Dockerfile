# 🔹 Imagen base ligera de Python
FROM python:3.11-slim

# 🔹 Variables de entorno
# Evita archivos .pyc y mejora logs en tiempo real
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 🔹 Crear usuario no-root (seguridad)
# Evita que la app corra como root dentro del contenedor
RUN adduser --disabled-password --gecos '' appuser

# 🔹 Directorio de trabajo dentro del contenedor
WORKDIR /app

# 🔹 Copiar solo requirements primero (optimiza cache de Docker)
COPY requirements.txt .

# 🔹 Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# 🔹 Copiar el resto del código
COPY . .

# 🔹 Dar permisos al usuario no-root sobre la app
RUN chown -R appuser:appuser /app

# 🔹 Cambiar a usuario seguro
USER appuser

# 🔹 Exponer puertos (documentativo)
EXPOSE 8000 8001

# 🔹 Comando por defecto (login)
# NOTA: docker-compose lo sobreescribe según servicio
CMD ["uvicorn", "login.login:app", "--host", "0.0.0.0", "--port", "8000"]