"""Histórico agregado de un sensor para las gráficas y los límites de Ajustes.

Un sensor manda una lectura por minuto: 30 días son ~43 000 puntos, demasiados para dibujar. Aquí
se agrupan por tramos de tiempo y de cada tramo se da el mínimo, la media, el máximo y cuántas
lecturas tuvo. Lo hace la propia base de datos en una sola consulta (no se traen las lecturas a
Python), apoyada en el índice (sensor, fecha).

Los tramos vacíos no se devuelven: un hueco en la lista es un hueco en los datos (sensor sin
señal) y la gráfica debe dibujarlo como tal, no como una línea que lo une.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import Integer, cast, func
from sqlmodel import select

from demeter.db import conexion
from demeter.models import SensorData

# Cuánto abarca cada rango y en qué tramos se agrupa (los puntos salen entre ~120 y ~170).
RANGES: dict[str, tuple[timedelta, timedelta]] = {
    "24h": (timedelta(hours=24), timedelta(minutes=10)),
    "7d": (timedelta(days=7), timedelta(hours=1)),
    "30d": (timedelta(days=30), timedelta(hours=6)),
}


@dataclass(frozen=True)
class Bucket:
    start: datetime  # inicio del tramo, UTC
    minimum: float
    average: float
    maximum: float
    count: int


def aggregate(sensor_id: str, range_: str, now: Optional[datetime] = None) -> tuple[datetime, datetime, timedelta, list[Bucket]]:
    """Lecturas del sensor en el rango, agrupadas. Devuelve ``(desde, hasta, tramo, tramos)``.

    El rango termina en ``now`` y los tramos se alinean al reloj (las 10:00, las 10:10…, o las
    horas en punto, o cada 6 h en UTC), así la gráfica no «baila» entre una petición y la
    siguiente. ``range_`` debe ser una clave de ``RANGES``.
    """
    span, step = RANGES[range_]
    until = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    since = until - span
    seconds = int(step.total_seconds())
    # Segundos desde 1970 (las fechas se guardan en UTC). El tramo es el primer segundo del tramo:
    # ``epoch - epoch % tramo`` (un ``epoch / tramo`` daría decimales, no una división entera).
    epoch = cast(func.strftime("%s", SensorData.recorded_at), Integer)
    bucket = (epoch - epoch % seconds).label("bucket")
    with conexion.open_session() as session:
        rows = session.exec(
            select(
                bucket,
                func.min(SensorData.value), func.sum(SensorData.value),
                func.max(SensorData.value), func.count(),
            )
            .where(SensorData.sensor_id == sensor_id)
            .where(SensorData.recorded_at >= since)
            .where(SensorData.recorded_at <= until)
            .group_by(bucket)
            .order_by(bucket)
        ).all()
    buckets = [
        Bucket(
            start=datetime.fromtimestamp(start, tz=timezone.utc),
            minimum=minimum, average=total / count, maximum=maximum, count=count,
        )
        for start, minimum, total, maximum, count in rows
    ]
    return since, until, step, buckets


def summarize(buckets: list[Bucket]) -> Optional[Bucket]:
    """Mínimo, media y máximo de todo el rango (``start`` es el del primer tramo). ``None`` sin datos."""
    if not buckets:
        return None
    count = sum(b.count for b in buckets)
    return Bucket(
        start=buckets[0].start,
        minimum=min(b.minimum for b in buckets),
        average=sum(b.average * b.count for b in buckets) / count,
        maximum=max(b.maximum for b in buckets),
        count=count,
    )
