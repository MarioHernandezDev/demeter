"""Conexión a la base de datos: motor (engine) y sesiones.

Es el único sitio que sabe a qué base de datos nos conectamos. El resto del
código (repositorio, simulador, seed) pide el motor aquí.
"""

import os

from sqlalchemy import event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, create_engine

# Misma variable y mismo valor por defecto que rxconfig.py: así Reflex/Alembic
# y nuestro código hablan siempre con la misma base de datos.
DEFAULT_URL = "sqlite:///data/demeter.db"


def database_url() -> str:
    """Dirección de la BD: ``DEMETER_DATABASE_URL`` o SQLite local."""
    return os.environ.get("DEMETER_DATABASE_URL", DEFAULT_URL)


def make_engine(url: str | None = None) -> Engine:
    """Crea el motor (engine) de conexión. ``url`` solo se pasa en pruebas."""
    url = url or database_url()
    target = make_url(url)
    options: dict = {}

    if target.get_backend_name() == "sqlite":
        # La API de FastAPI atiende cada petición en un hilo distinto, y por
        # defecto SQLite prohíbe usar una conexión desde otro hilo que la creó.
        options["connect_args"] = {"check_same_thread": False}

        if target.database in (None, "", ":memory:"):
            # BD en memoria (pruebas): cada conexión nueva sería una BD vacía
            # distinta. StaticPool obliga a reutilizar siempre la misma.
            options["poolclass"] = StaticPool
        else:
            # SQLite crea el fichero .db pero NO la carpeta que lo contiene.
            os.makedirs(os.path.dirname(os.path.abspath(target.database)), exist_ok=True)

    engine = create_engine(url, **options)

    if target.get_backend_name() == "sqlite":

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            # SQLite NO comprueba las claves foráneas salvo que se le pida, y
            # hay que pedirlo en CADA conexión nueva (no queda guardado en el
            # fichero). Sin esto, se podría guardar una alerta de un sensor
            # que no existe y la base de datos no diría nada.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


# Motor compartido por toda la aplicación. Se crea la primera vez que se pide
# (y no al importar el módulo) para no tocar el disco antes de tiempo.
_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = make_engine()
    return _engine


def open_session() -> Session:
    """Sesión nueva. Uso: ``with open_session() as s: ...``"""
    return Session(get_engine())