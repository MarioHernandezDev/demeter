"""Reglas de las alertas: cuándo se abren y cuándo se cierran (D1, issue #36).

Es el contrato de alertas en código. Explicación completa y ejemplos en
``docs/alertas-contrato.md``. Aquí solo hay funciones puras (sin base de datos ni
red), para que el motor (D2, ``services/alerts.py``), el dashboard (D3) y los tests
(D7) usen exactamente las mismas reglas.

Resumen:
- **Abre** ``LOW`` si ``valor < umbral_bajo`` y ``HIGH`` si ``valor > umbral_alto``
  (igual que ``Sensor.status_for`` en ``demeter/state/types.py``).
- **No duplica**: como mucho una alerta activa por sensor y tipo.
- **Cierra** con histéresis: el valor tiene que volver un 2 % del rango del sensor
  hacia dentro del umbral. Así un valor que baila sobre el umbral no abre y cierra
  alertas sin parar.
- **OFFLINE**: un sensor activo que lleva 10 min sin enviar datos.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

# Margen de cierre: 2 % del rango del sensor (umbral_alto - umbral_bajo).
HYSTERESIS = 0.02
# Sin lecturas durante este tiempo, el sensor está offline.
OFFLINE_AFTER = timedelta(minutes=10)
# Cada cuánto busca el motor sensores offline.
OFFLINE_CHECK_EVERY = timedelta(seconds=60)
# Estado de tarjeta para un sensor offline (propuesto para ``SensorStatus``).
STATUS_OFFLINE = "offline"


class AlertKind(str, Enum):
    """Tipo de alerta. ``OFFLINE`` es nuevo respecto a ``AlertType`` (LOW/HIGH)."""

    LOW = "LOW"
    HIGH = "HIGH"
    OFFLINE = "OFFLINE"


@dataclass(frozen=True)
class Decision:
    """Qué tiene que hacer el motor con una lectura: cerrar una alerta, abrir otra, o nada."""

    close: Optional[AlertKind] = None
    open: Optional[AlertKind] = None

    @property
    def nothing(self) -> bool:
        return self.close is None and self.open is None


def margin(low: Optional[float], high: Optional[float]) -> float:
    """Margen de histéresis en las unidades del sensor.

    Con los dos umbrales: 2 % de ``high - low`` (no depende de dónde esté el cero,
    así funciona igual con 2 ºC que con 35 ºC). Con un solo umbral: 2 % de su valor
    absoluto. Sin umbrales: 0.
    """
    # Se redondea para que 25 + 0,7 sea 25,7 y no 25,700000000000003.
    if low is not None and high is not None:
        return round(HYSTERESIS * abs(high - low), 6)
    only = low if low is not None else high
    return round(HYSTERESIS * abs(only), 6) if only is not None else 0.0


def breach(value: float, low: Optional[float], high: Optional[float]) -> Optional[AlertKind]:
    """¿Esta lectura está fuera de umbrales? Los umbrales exactos todavía son normales."""
    if low is not None and value < low:
        return AlertKind.LOW
    if high is not None and value > high:
        return AlertKind.HIGH
    return None


def is_cleared(kind: AlertKind, value: float, low: Optional[float], high: Optional[float]) -> bool:
    """¿Una alerta activa de tipo ``kind`` se puede cerrar con esta lectura?

    ``LOW`` se cierra con ``value >= low + margen``; ``HIGH`` con ``value <= high - margen``.
    Si ya no hay umbral en ese lado (lo quitó el admin), se cierra. ``OFFLINE`` se
    cierra con cualquier lectura.
    """
    m = margin(low, high)
    if kind is AlertKind.LOW:
        return low is None or value >= low + m
    if kind is AlertKind.HIGH:
        return high is None or value <= high - m
    return True


def decide(
    active: Optional[AlertKind], value: float, low: Optional[float], high: Optional[float]
) -> Decision:
    """Regla completa para una lectura nueva de un sensor activo.

    ``active`` es la alerta de umbral (``LOW`` o ``HIGH``) que el sensor tiene abierta,
    o ``None``. Las ``OFFLINE`` se tratan aparte: cualquier lectura las cierra.
    """
    if active is AlertKind.OFFLINE:
        raise ValueError("Las alertas OFFLINE no pasan por decide(): las cierra cualquier lectura")
    close = active if active is not None and is_cleared(active, value, low, high) else None
    still_open = active if close is None else None
    new = breach(value, low, high)
    open_ = new if new is not None and new is not still_open else None
    return Decision(close=close, open=open_)


def is_offline(last_reading: Optional[datetime], now: datetime) -> bool:
    """Un sensor está offline si su última lectura tiene 10 min o más.

    Un sensor que nunca ha enviado datos no se considera offline (su tarjeta dice
    «sin datos»), para no llenar de alertas una base de datos recién creada.
    """
    return last_reading is not None and now - last_reading >= OFFLINE_AFTER


def card_status(
    value: Optional[float],
    last_reading: Optional[datetime],
    now: datetime,
    low: Optional[float],
    high: Optional[float],
) -> str:
    """Semáforo de la tarjeta del dashboard: ``offline`` gana a ``LOW``/``HIGH``/``ok``."""
    if value is None or last_reading is None:
        return "sin_datos"
    if is_offline(last_reading, now):
        return STATUS_OFFLINE
    kind = breach(value, low, high)
    return kind.value if kind is not None else "ok"


def fmt_number(x: float) -> str:
    """Número para un mensaje en español: ``23,7``, ``25`` (sin ``,0``)."""
    text = f"{x:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def message(kind: AlertKind, value: Optional[float] = None, unit: str = "",
            threshold: Optional[float] = None) -> str:
    """Texto de la alerta, que se guarda al abrirla. No lleva el sensor: va en su columna.

    >>> message(AlertKind.LOW, 19, "%", 25)
    '19 % por debajo del umbral (25 %)'
    """
    if kind is AlertKind.OFFLINE:
        minutes = int(OFFLINE_AFTER.total_seconds() // 60)
        return f"Sin datos desde hace más de {minutes} min"
    side = "por debajo del" if kind is AlertKind.LOW else "por encima del"
    u = f" {unit}" if unit else ""
    return f"{fmt_number(value)}{u} {side} umbral ({fmt_number(threshold)}{u})"
