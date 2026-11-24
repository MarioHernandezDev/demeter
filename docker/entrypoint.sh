#!/bin/sh
# Arranque del contenedor: migra la base de datos, carga los datos de ejemplo y levanta la app.
# Las dos primeras cosas se pueden repetir sin miedo (solo hacen lo que falta).
set -e

echo "› Migrando la base de datos ($DEMETER_DATABASE_URL)"
reflex db migrate

if [ "${DEMETER_SEED:-1}" = "1" ]; then
    echo "› Cargando datos de ejemplo de la Costa Tropical"
    python -m demeter.db.seed
fi

echo "› Demeter en http://localhost:${PORT:-3000}"
exec reflex run --env prod --single-port --frontend-port "${PORT:-3000}" --backend-host 0.0.0.0 "$@"
