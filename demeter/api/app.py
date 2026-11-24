"""Aplicación FastAPI de Demeter.

Arrancar sola (para probar y ver ``/docs``)::

    uvicorn demeter.api.app:api --reload

Dentro de Reflex se engancha con ``rx.App(api_transformer=demeter.api.app.api)``
(se hace al integrar con el esqueleto de Reflex, ver docs/api-contrato.md).
"""

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from demeter.api.routes import VERSION, router
from demeter.services.alerts import vigilar_offline


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Al arrancar la API, lanza la comprobación de sensores OFFLINE cada 60 s
    (motor de alertas, D2). ``DEMETER_SIN_VIGILANCIA=1`` la desactiva (pruebas)."""
    tarea = None
    if os.environ.get("DEMETER_SIN_VIGILANCIA") != "1":
        tarea = asyncio.create_task(vigilar_offline())
    yield
    if tarea is not None:
        tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await tarea


api = FastAPI(
    lifespan=lifespan,
    title="Demeter API",
    version=VERSION,
    description=(
        "Contrato de la API de Demeter con **datos de ejemplo** (nada se guarda). "
        "Para probar en /docs: `POST /api/auth/login` con `admin` / `demo1234` y pega el "
        "`access_token` en «Authorize»."
    ),
)
api.include_router(router)


@api.exception_handler(OperationalError)
def database_not_ready(_: Request, __: OperationalError):
    """Sin tablas (o sin fichero) las rutas que usan la BD fallarían con un 500 sin explicación."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": "La base de datos no está preparada. Ejecuta `reflex db migrate` y "
            "`python -m demeter.db.seed`."
        },
    )
