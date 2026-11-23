"""Modelo de la tabla ``users`` (docs/modelo-datos.md, sección 3.1)."""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from .base import ahora_utc


class User(SQLModel, table=True):
    """Persona que puede entrar en la aplicación."""

    __tablename__ = "users"

    # Un usuario sin contraseña Y sin cuenta de Google no podría entrar nunca:
    # sería una fila inservible. La base de datos lo impide, en vez de confiar
    # en que el código de registro nunca falle.
    __table_args__ = (
        sa.CheckConstraint(
            "password_hash IS NOT NULL OR google_sub IS NOT NULL",
            name="ck_users_tiene_credencial",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)

    # Obligatorio y único. Se guarda SIEMPRE en minúsculas (lo normaliza el
    # código antes de guardar), porque SQLite distingue mayúsculas al comparar
    # y "Ana@x.com" y "ana@x.com" serían dos cuentas distintas.
    email: str = Field(unique=True, index=True)

    # Falso hasta que la persona pulsa el enlace del correo. Es independiente
    # de ``is_active``: ese lo decide un administrador (baja), este lo decide
    # el correo. Mezclarlos permitiría que un usuario dado de baja se
    # reactivara solo verificando su correo.
    email_verified: bool = Field(default=False)

    # Vacío si la cuenta solo entra con Google.
    password_hash: str | None = Field(default=None)

    # Identificador estable de la cuenta de Google (el campo "sub" de su
    # token). Las cuentas de Google se enlazan SOLO por aquí, nunca por email:
    # si no, alguien podría registrarse con el correo de otra persona y
    # quedarse con su cuenta. Único; vacío si no usa Google. SQLite permite
    # varias filas con valor vacío en una columna única.
    google_sub: str | None = Field(default=None, unique=True, index=True)

    role: str
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=ahora_utc)
