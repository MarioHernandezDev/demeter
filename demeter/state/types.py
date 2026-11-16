"""Tipos de datos que la interfaz recibe de la API (contrato C1, issue #28).

Son el «idioma común» entre el backend (A*) y el frontend (C*): cada clase refleja
una tabla del reto y la forma JSON que devuelven los endpoints. Si alguien cambia un
campo aquí, debe cambiarlo también en la API: por eso la issue lleva la etiqueta
«contrato» y cualquier cambio necesita el acuerdo del equipo.

Notas de diseño:
- Son dataclasses inmutables (frozen). Reflex 0.11 las admite como tipo de las
  variables de estado (``list[Reading]``, ``Sensor | None``…) y así nadie modifica
  por error un dato que vino de la API: para cambiarlo, se vuelve a pedir.
- Los ``from_api`` convierten el diccionario JSON en el objeto. Ignoran claves que no
  conocen, para que añadir un campo en la API no rompa la interfaz.
- Las fechas viajan como texto ISO 8601 en UTC (``"2026-11-16T10:02:00Z"``), tal y
  como sugiere el reto; la conversión a hora local se hace solo al mostrarlas.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any


class Role(str, Enum):
    """Rol del usuario: ``admin`` puede editar umbrales; ``tecnico`` solo consulta.

    En los datos se guarda el texto (``Role.ADMIN.value == "admin"``).
    """

    ADMIN = "admin"
    TECNICO = "tecnico"


class SensorType(str, Enum):
    """Magnitudes que mide Demeter (columna ``sensors.type``)."""

    TEMPERATURA = "temperatura"
    HUMEDAD_SUELO = "humedad_suelo"
    LUMINOSIDAD = "luminosidad"
    HUMEDAD_AMBIENTE = "humedad_ambiente"


class AlertType(str, Enum):
    """Sentido en que un valor se sale de sus umbrales (columna ``alerts.type``)."""

    LOW = "LOW"
    HIGH = "HIGH"


class SensorStatus(str, Enum):
    """Estado de un sensor según su último valor. Lo calcula ``Sensor.status_for``."""

    OK = "ok"
    LOW = "LOW"
    HIGH = "HIGH"
    SIN_DATOS = "sin_datos"


def _pick(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Se queda solo con las claves del JSON que existen como campo de ``cls``."""
    names = {f.name for f in dataclasses.fields(cls)}
    return {k: v for k, v in data.items() if k in names}


@dataclasses.dataclass(frozen=True)
class User:
    """Usuario con sesión iniciada (tabla ``users``, sin la contraseña)."""

    id: int
    username: str
    role: str = Role.TECNICO.value

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> User:
        return cls(**_pick(cls, data))


@dataclasses.dataclass(frozen=True)
class LoginResponse:
    """Respuesta de ``POST /api/auth/login``."""

    access_token: str
    token_type: str = "bearer"
    user: User | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> LoginResponse:
        user = data.get("user")
        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            user=User.from_api(user) if user else None,
        )


@dataclasses.dataclass(frozen=True)
class Parcel:
    """Parcela o finca (tabla ``parcels``). ``GET /api/parcels``."""

    id: int
    name: str
    location: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Parcel:
        return cls(**_pick(cls, data))


@dataclasses.dataclass(frozen=True)
class Sensor:
    """Sensor de una parcela (tabla ``sensors``). ``GET /api/parcels/{id}/sensors``.

    ``threshold_low`` / ``threshold_high`` pueden ser ``None`` si ese lado no tiene
    umbral (p. ej. una temperatura máxima sin mínima).
    """

    id: str  # p. ej. "t001"
    parcel_id: int
    type: str  # uno de SensorType
    unit: str  # "ºC", "%", "klx"…
    description: str = ""
    threshold_low: float | None = None
    threshold_high: float | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Sensor:
        return cls(**_pick(cls, data))

    def status_for(self, value: float | None) -> str:
        """Compara un valor con los umbrales de este sensor."""
        if value is None:
            return SensorStatus.SIN_DATOS.value
        if self.threshold_low is not None and value < self.threshold_low:
            return SensorStatus.LOW.value
        if self.threshold_high is not None and value > self.threshold_high:
            return SensorStatus.HIGH.value
        return SensorStatus.OK.value


@dataclasses.dataclass(frozen=True)
class Reading:
    """Una lectura de un sensor (tabla ``sensor_data``).

    Es el formato de ``GET /api/sensors/{sensor_id}/data`` que da el reto:
    ``{"sensor_id": "t001", "timestamp": "...Z", "type": "temperatura",
    "value": 23.7, "unit": "ºC"}``.
    """

    sensor_id: str
    timestamp: str  # ISO 8601 UTC
    value: float
    type: str = ""
    unit: str = ""

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Reading:
        return cls(**_pick(cls, data))


@dataclasses.dataclass(frozen=True)
class Alert:
    """Alerta generada cuando una lectura sale de sus umbrales (tabla ``alerts``)."""

    id: int
    sensor_id: str
    timestamp: str  # ISO 8601 UTC
    type: str  # uno de AlertType
    message: str
    acknowledged: bool = False

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Alert:
        return cls(**_pick(cls, data))


@dataclasses.dataclass(frozen=True)
class SensorSnapshot:
    """Un sensor con su última lectura: cada tarjeta del dashboard."""

    sensor: Sensor
    last: Reading | None = None
    status: str = SensorStatus.SIN_DATOS.value

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> SensorSnapshot:
        sensor = Sensor.from_api(data["sensor"])
        last = Reading.from_api(data["last"]) if data.get("last") else None
        return cls(
            sensor=sensor,
            last=last,
            status=data.get("status") or sensor.status_for(last.value if last else None),
        )


@dataclasses.dataclass(frozen=True)
class DashboardSummary:
    """Respuesta de ``GET /api/dashboard``: último valor por sensor y alertas abiertas."""

    parcel: Parcel
    sensors: list[SensorSnapshot] = dataclasses.field(default_factory=list)
    alerts: list[Alert] = dataclasses.field(default_factory=list)
    unread_alerts: int = 0
    updated_at: str = ""  # ISO 8601 UTC del dato más reciente

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> DashboardSummary:
        alerts = [Alert.from_api(a) for a in data.get("alerts", [])]
        return cls(
            parcel=Parcel.from_api(data["parcel"]),
            sensors=[SensorSnapshot.from_api(s) for s in data.get("sensors", [])],
            alerts=alerts,
            unread_alerts=data.get("unread_alerts", sum(not a.acknowledged for a in alerts)),
            updated_at=data.get("updated_at", ""),
        )


@dataclasses.dataclass(frozen=True)
class HistoryQuery:
    """Filtros del histórico: ``GET /api/sensors/{id}/data?from=&to=&limit=``."""

    sensor_id: str
    from_: str | None = None  # ISO 8601; «from» es palabra reservada en Python
    to: str | None = None
    limit: int = 500

    def params(self) -> dict[str, str | int]:
        """Parámetros de la URL, sin los vacíos."""
        out: dict[str, str | int] = {"limit": self.limit}
        if self.from_:
            out["from"] = self.from_
        if self.to:
            out["to"] = self.to
        return out
