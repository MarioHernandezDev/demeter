"""Modelo de la tabla ``sensor_data`` (docs/modelo-datos.md, sección 3.4)."""

from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


class SensorData(SQLModel, table=True):
    """Una lectura de un sensor. Es la tabla con más filas del sistema."""

    __tablename__ = "sensor_data"

    # Índice ÚNICO sobre (sensor_id, recorded_at), en ese orden. Hace dos cosas:
    #  1. Impide guardar dos veces la misma lectura (mismo sensor, mismo instante).
    #  2. Acelera la consulta típica: "lecturas de ESTE sensor entre estas
    #     fechas". El orden importa: primero el sensor, luego la fecha. Un
    #     índice (sensor, fecha) sirve para buscar por sensor, o por sensor y
    #     fecha, pero no para buscar solo por fecha.
    # Le damos nombre propio para poder referirnos a él en migraciones futuras.
    __table_args__ = (
        sa.Index(
            "uq_sensor_data_sensor_recorded",
            "sensor_id",
            "recorded_at",
            unique=True,
        ),
    )

    id: int | None = Field(default=None, primary_key=True)

    # Clave foránea de TEXTO: apunta al código del sensor ("t001").
    sensor_id: str = Field(foreign_key="sensors.id")

    # Cuándo se TOMÓ la medida (UTC), no cuándo se guardó. Sin valor por
    # defecto: lo manda el sensor. Si usáramos "ahora", una lectura atrasada
    # (backfill) quedaría con la fecha equivocada.
    recorded_at: datetime

    value: float