# Imagen de la interfaz web de KOPERA.
#
# El contexto de build es la RAIZ del repositorio (ver docker-compose.app.yml),
# porque el Dockerfile referencia Kopera/app/. El .dockerignore de la raiz deja
# fuera .venv, docs y credenciales.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Las dependencias se copian primero y se instalan aparte: mientras no cambien,
# Docker reutiliza la capa y el rebuild es casi instantaneo.
COPY Kopera/app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Codigo de la app
COPY Kopera/app/ ./

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "main.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0"]
