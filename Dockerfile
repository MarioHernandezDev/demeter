# Demeter en un contenedor (E9, issue #4): plan B para la final.
#
#   docker compose up --build      → http://localhost:3000  (web, /api y /docs en el mismo puerto)
#
# La interfaz se compila al construir la imagen, así el arranque es rápido y no necesita internet.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    REFLEX_TELEMETRY_ENABLED=false

# Reflex descarga bun y node para compilar la interfaz: necesita curl y unzip.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Primero las dependencias: esta capa solo se rehace si cambia requirements.txt.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Compila la interfaz de producción dentro de la imagen.
RUN reflex export --frontend-only --no-zip --env prod \
    && chmod +x docker/entrypoint.sh

EXPOSE 3000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:3000/api/health || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
