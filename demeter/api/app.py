"""Aplicación FastAPI de Demeter.

Arrancar sola (para probar y ver ``/docs``)::

    uvicorn demeter.api.app:api --reload

Dentro de Reflex se engancha con ``rx.App(api_transformer=demeter.api.app.api)``
(se hace al integrar con el esqueleto de Reflex, ver docs/api-contrato.md).
"""

from fastapi import FastAPI

from demeter.api.routes import VERSION, router

api = FastAPI(
    title="Demeter API",
    version=VERSION,
    description=(
        "Contrato de la API de Demeter con **datos de ejemplo** (nada se guarda). "
        "Para probar en /docs: `POST /api/auth/login` con `admin` / `demo1234` y pega el "
        "`access_token` en «Authorize»."
    ),
)
api.include_router(router)
