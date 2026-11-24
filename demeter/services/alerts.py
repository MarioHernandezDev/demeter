"""Motor de alertas (D2, issue #37).

Aplica las reglas de ``alert_rules.py`` (D1) contra la base de datos:

- ``evaluar_lectura``: lo llama la ingesta (A5) después de guardar una lectura
  nueva. Abre ``LOW``/``HIGH``, no las duplica, las cierra con histéresis al
  normalizarse y cierra la ``OFFLINE`` del sensor si la tenía.
- ``comprobar_offline``: lo llama una tarea cada 60 s (``iniciar_vigilancia_offline``).
  Abre ``OFFLINE`` en los sensores activos que llevan 10 min o más sin datos.
- ``cerrar_alertas_sensor``: al desactivar un sensor se cierran sus alertas activas.

Ninguna función hace ``commit``: trabajan dentro de la sesión (transacción) de
quien las llama, para que la lectura y sus alertas se guarden juntas o no se
guarde nada (contrato de alertas, sección 8, punto 9). Todas devuelven las
alertas que acaban de abrir, por si alguien quiere avisar de ellas.

Fechas: se reciben con o sin zona horaria (sin zona = UTC) y se guardan en UTC
con zona, como pide el modelo de datos.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, col, select

from demeter.models import Alert, Parcel, Sensor
from demeter.services.alert_rules import (
    OFFLINE_CHECK_EVERY,
    AlertKind,
    decide,
    is_offline,
    message,
)

log = logging.getLogger(__name__)

_UMBRAL = (AlertKind.LOW.value, AlertKind.HIGH.value)


def utc(dt: datetime) -> datetime:
    """Fecha en UTC con zona horaria. Una fecha sin zona (SQLite las devuelve
    así) se entiende como UTC, que es como se guarda todo."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ahora() -> datetime:
    return utc(datetime.now(timezone.utc))


# ------------------------------------------------------------------ consultas


def alertas_activas(session: Session, sensor_id: str) -> dict[str, Alert]:
    """Alertas activas del sensor, por tipo (como mucho una por tipo)."""
    filas = session.exec(
        select(Alert).where(Alert.sensor_id == sensor_id, col(Alert.resolved_at).is_(None))
    ).all()
    return {a.type: a for a in filas}


def _abrir(session: Session, sensor_id: str, kind: AlertKind, cuando: datetime, texto: str,
           value: Optional[float] = None, threshold: Optional[float] = None) -> Alert:
    alerta = Alert(sensor_id=sensor_id, type=kind.value, opened_at=cuando, message=texto,
                   value=value, threshold=threshold)
    session.add(alerta)
    return alerta


def _cerrar(session: Session, alerta: Alert, cuando: datetime) -> None:
    alerta.resolved_at = cuando
    session.add(alerta)


# ------------------------------------------------------------------ lecturas


def evaluar_lectura(session: Session, sensor_id: str, recorded_at: datetime,
                    value: float) -> list[Alert]:
    """Evalúa una lectura recién guardada. Devuelve las alertas que abre.

    No evalúa (devuelve ``[]``) si el sensor no existe, está desactivado o la
    lectura es más antigua que la última conocida del sensor (backfill): el
    histórico no genera alertas.
    """
    sensor = session.get(Sensor, sensor_id)
    if sensor is None or not sensor.is_active:
        return []
    cuando = utc(recorded_at)
    if sensor.last_seen_at is not None and cuando < utc(sensor.last_seen_at):
        return []

    activas = alertas_activas(session, sensor_id)

    # Cualquier lectura cierra la OFFLINE.
    offline = activas.pop(AlertKind.OFFLINE.value, None)
    if offline is not None:
        _cerrar(session, offline, cuando)

    low, high = sensor.threshold_low, sensor.threshold_high

    # Normalmente hay como mucho una de umbral; si por un fallo hubiera dos,
    # la que ya no se cumple se cierra igualmente.
    abiertas: list[Alert] = []
    if len(activas) > 1:
        for tipo in list(activas):
            if decide(AlertKind(tipo), value, low, high).close is not None:
                _cerrar(session, activas.pop(tipo), cuando)

    actual = next(iter(activas.values()), None)
    d = decide(AlertKind(actual.type) if actual else None, value, low, high)
    if d.close is not None and actual is not None:
        _cerrar(session, actual, cuando)
    # decide() nunca pide abrir el tipo que sigue activo: no hay duplicados.
    if d.open is not None:
        umbral = low if d.open is AlertKind.LOW else high
        abiertas.append(_abrir(session, sensor_id, d.open, cuando,
                               message(d.open, value, sensor.unit, umbral),
                               value=value, threshold=umbral))
    session.flush()
    return abiertas


# ------------------------------------------------------------------ offline


def comprobar_offline(session: Session, now: Optional[datetime] = None) -> list[Alert]:
    """Abre ``OFFLINE`` en los sensores activos (de parcelas activas) sin datos
    desde hace 10 min o más. Los que nunca han enviado datos no cuentan."""
    now = utc(now) if now is not None else ahora()
    sensores = session.exec(
        select(Sensor)
        .join(Parcel, col(Parcel.id) == col(Sensor.parcel_id))
        .where(col(Sensor.is_active).is_(True), col(Parcel.is_active).is_(True),
               col(Sensor.last_seen_at).is_not(None))
    ).all()
    ya_offline = set(session.exec(
        select(Alert.sensor_id).where(Alert.type == AlertKind.OFFLINE.value,
                                      col(Alert.resolved_at).is_(None))
    ).all())

    abiertas = [
        _abrir(session, s.id, AlertKind.OFFLINE, now, message(AlertKind.OFFLINE))
        for s in sensores
        if s.id not in ya_offline and is_offline(utc(s.last_seen_at), now)
    ]
    session.flush()
    return abiertas


def cerrar_alertas_sensor(session: Session, sensor_id: str,
                          now: Optional[datetime] = None) -> int:
    """Cierra todas las alertas activas de un sensor (p. ej. al desactivarlo).
    Devuelve cuántas ha cerrado."""
    now = utc(now) if now is not None else ahora()
    activas = alertas_activas(session, sensor_id)
    for alerta in activas.values():
        _cerrar(session, alerta, now)
    session.flush()
    return len(activas)


# ------------------------------------------------------------------ tarea periódica


def _comprobar_y_guardar() -> list[Alert]:
    from demeter.db.conexion import open_session

    with open_session() as session:
        abiertas = comprobar_offline(session)
        session.commit()
        return abiertas


async def vigilar_offline(cada: float = OFFLINE_CHECK_EVERY.total_seconds()) -> None:
    """Bucle infinito: busca sensores offline cada ``cada`` segundos.

    Un fallo (BD sin migrar, bloqueada...) se registra y el bucle sigue.
    """
    while True:
        try:
            abiertas = await asyncio.to_thread(_comprobar_y_guardar)
            if abiertas:
                log.info("OFFLINE: %s", ", ".join(a.sensor_id for a in abiertas))
        except Exception:  # noqa: BLE001 - la vigilancia no debe morir
            log.exception("Fallo al comprobar sensores offline")
        await asyncio.sleep(cada)
