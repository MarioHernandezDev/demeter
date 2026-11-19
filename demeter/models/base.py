"""Utilidades comunes a todos los modelos."""

from datetime import datetime, timezone


def ahora_utc() -> datetime:
    """Fecha y hora actuales en UTC.

    Se guarda siempre en UTC (decisión del documento de modelo de datos) para
    evitar líos con horarios de verano y zonas horarias. La conversión a hora
    local se hace al mostrarlo en pantalla, no al guardarlo.
    """
    return datetime.now(timezone.utc)