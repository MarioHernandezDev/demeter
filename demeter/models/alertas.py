"""Modelo de la tabla ``alerts`` (docs/modelo-datos.md, sección 3.5)."""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class Alert(SQLModel, table=True):
    """Aviso del motor de alertas: se abre, dura un tiempo y se resuelve."""

    __tablename__ = "alerts"

    # Índice único PARCIAL: solo cuenta las filas con ``resolved_at`` vacío,
    # es decir, las alertas activas. Resultado: un sensor puede tener como
    # mucho UNA alerta activa de cada tipo, pero todas las resueltas que
    # quieras en el historial. Lo garantiza la propia base de datos aunque el
    # código de las alertas tenga un fallo.
    # ``sqlite_where`` es lo que lo hace parcial en SQLite. Ojo: otros motores
    # (MySQL, por ejemplo) no tienen índices parciales; si algún día se
    # cambia de motor, esto habría que revisarlo.
    __table_args__ = (
        sa.Index(
            "uq_alerts_activa",
            "sensor_id",
            "type",
            unique=True,
            sqlite_where=sa.text("resolved_at IS NULL"),
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    sensor_id: str = Field(foreign_key="sensors.id")

    # ``LOW`` | ``HIGH`` | ``OFFLINE``. Se valida en la aplicación.
    type: str

    opened_at: datetime

    # Cuándo la resolvió el SISTEMA. Vacío = sigue activa. No hay columna
    # "estado": activa o resuelta se deduce de este campo, para no guardar
    # lo mismo en dos sitios que podrían contradecirse.
    resolved_at: datetime | None = Field(default=None)

    # Texto del aviso, generado al abrir la alerta.
    message: str

    # Si una PERSONA la ha marcado como leída. Es independiente de
    # ``resolved_at``: una alerta puede estar resuelta pero sin leer, o
    # leída pero aún activa.
    acknowledged: bool = Field(default=False)

    # Valor y umbral que la dispararon. Vacíos en las OFFLINE, que no
    # dependen de un valor medido.
    value: float | None = Field(default=None)
    threshold: float | None = Field(default=None)