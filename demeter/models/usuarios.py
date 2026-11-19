"""Modelo de la tabla ``users`` (docs/modelo-datos.md, sección 3.1).

Usamos SQLModel directamente y no ``rx.Model``: este último está deprecado
desde Reflex 0.9.2 y se eliminará en la 1.0, así que no nos conviene
construir toda la base de datos encima.
"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel

from .base import ahora_utc


class User(SQLModel, table=True):
    """Persona que puede entrar en la aplicación."""

    # Nombre real de la tabla en la base de datos. Lo fijamos a mano para que
    # coincida con el documento (``users``) y no dependa del nombre de la clase.
    __tablename__ = "users"

    # Clave primaria. Es ``None`` hasta que se guarda: entonces la base de
    # datos le asigna el número siguiente (autoincremental).
    id: int | None = Field(default=None, primary_key=True)

    # Con ``unique=True`` la base de datos rechaza dos usuarios con el mismo
    # nombre, aunque falle el código de la aplicación. ``index=True`` hace que
    # buscar por username (cada vez que alguien inicia sesión) sea rápido.
    username: str = Field(unique=True, index=True)

    # Opcional: el login es por username, el correo es solo de contacto.
    email: str | None = Field(default=None)

    # Nunca se guarda la contraseña, solo su huella bcrypt: aunque alguien
    # viera la base de datos, no podría leer las contraseñas.
    password_hash: str

    # ``admin`` | ``tecnico`` | ``lector``. Se valida en la aplicación; aquí
    # es solo texto (SQLite no tiene tipo "lista cerrada").
    role: str

    # Desactivar en vez de borrar (decisión 24 del documento): así se conserva
    # el historial. Si es False, el usuario no puede entrar.
    is_active: bool = Field(default=True)

    # Fecha de alta, rellenada sola al crear el usuario.
    created_at: datetime = Field(default_factory=ahora_utc)