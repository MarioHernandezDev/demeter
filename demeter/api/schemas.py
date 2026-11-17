"""Contrato de la API de Demeter: todos los esquemas de entrada y salida (A1, issue #20).

Es el «idioma común» entre la API y la interfaz. Para lo que ya existía, los nombres y
la forma JSON son los de ``demeter/state/types.py`` (el contrato de la interfaz, C1):
si ese fichero ya tiene un campo, aquí se llama igual. Los campos nuevos son opcionales
o van en modelos nuevos, de modo que la interfaz actual (cuyos ``from_api`` ignoran las
claves que no conocen) sigue funcionando sin tocar nada.

Reglas generales:
- Fechas y horas: ISO 8601 en UTC, con ``Z`` al final (``2026-11-16T10:02:00Z``).
- Coordenadas: latitud/longitud (WGS84). En GeoJSON el orden es ``[longitud, latitud]``.
- Superficies en m², volúmenes en litros, importes en euros.
- Los ids de sensor son texto (``"t001"``, formato del reto); el resto de ids son enteros.
"""

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------------------
# Listas cerradas
# --------------------------------------------------------------------------------------

Role = Literal["admin", "tecnico", "lector"]
# Los cuatro primeros son los del reto y de la interfaz. ``nivel_deposito`` es nuevo:
# el nivel de un depósito se trata como un sensor más (decisión del modelo de datos).
SensorType = Literal[
    "temperatura", "humedad_suelo", "luminosidad", "humedad_ambiente", "nivel_deposito"
]
AlertType = Literal["LOW", "HIGH", "OFFLINE"]
SensorStatus = Literal["ok", "LOW", "HIGH", "sin_datos"]
ZoneType = Literal["crop", "no_crop"]
ElementType = Literal["tree", "terrace", "path"]
TransactionKind = Literal["income", "expense"]


# --------------------------------------------------------------------------------------
# Geometría (GeoJSON)
# --------------------------------------------------------------------------------------


class Polygon(BaseModel):
    """Polígono GeoJSON. ``coordinates[0]`` es el anillo exterior: ``[[lon, lat], ...]``."""

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]] = Field(min_length=1)


class Geometry(BaseModel):
    """Forma de un elemento del terreno: punto (árbol), línea (camino) o polígono (bancal)."""

    type: Literal["Point", "LineString", "Polygon"]
    coordinates: Any


# --------------------------------------------------------------------------------------
# Autenticación y usuarios (A3, issue #21)
# --------------------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Cuerpo de ``POST /api/auth/login``."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class User(BaseModel):
    """Usuario con sesión iniciada (sin contraseña)."""

    id: int
    username: str
    role: Role = "tecnico"
    is_active: bool = True


class LoginResponse(BaseModel):
    """Respuesta de ``POST /api/auth/login``."""

    access_token: str
    token_type: str = "bearer"
    user: Optional[User] = None


class UserCreate(BaseModel):
    """Cuerpo de ``POST /api/users`` (solo admin)."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=8)
    role: Role = "tecnico"


class UserUpdate(BaseModel):
    """Cuerpo de ``PATCH /api/users/{id}`` (solo admin). Desactivar no borra al usuario."""

    role: Optional[Role] = None
    is_active: Optional[bool] = None


# --------------------------------------------------------------------------------------
# Parcelas, sensores y lecturas
# --------------------------------------------------------------------------------------


class Parcel(BaseModel):
    """Parcela o finca. ``GET /api/parcels``."""

    id: int
    name: str
    location: str = ""
    crop: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    area_m2: Optional[float] = None


class ParcelDetail(Parcel):
    """Parcela con su contorno. ``GET /api/parcels/{id}``."""

    boundary: Optional[Polygon] = None


class Sensor(BaseModel):
    """Sensor de una parcela. ``GET /api/parcels/{id}/sensors``.

    Los umbrales pueden ser ``null`` si ese lado no tiene umbral.
    """

    id: str  # p. ej. "t001"
    parcel_id: int
    type: SensorType
    unit: str  # "ºC", "%", "klx"
    description: str = ""
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None
    latitude: Optional[float] = None  # dónde está instalado (necesario para dibujarlo en el 3D)
    longitude: Optional[float] = None
    is_active: bool = True


class SensorUpdate(BaseModel):
    """Cuerpo de ``PATCH /api/sensors/{id}``. Solo se cambian los campos enviados.

    Cambiar umbrales: solo admin. Colocar el sensor en el mapa (latitud/longitud): admin o tecnico.
    """

    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None


class Reading(BaseModel):
    """Una lectura. Formato de ``GET /api/sensors/{sensor_id}/data`` dado por el reto."""

    sensor_id: str
    timestamp: datetime
    value: float
    type: str = ""
    unit: str = ""


class ReadingIn(BaseModel):
    """Cuerpo de ``POST /api/sensors/{sensor_id}/data`` (ingesta, cabecera ``X-API-Key``)."""

    timestamp: datetime
    value: float


class IngestResult(BaseModel):
    """Respuesta de la ingesta. ``duplicate`` es verdadero si esa lectura ya existía (se ignora)."""

    sensor_id: str
    timestamp: datetime
    stored: bool
    duplicate: bool = False


# --------------------------------------------------------------------------------------
# Alertas y dashboard
# --------------------------------------------------------------------------------------


class Alert(BaseModel):
    """Alerta abierta por el motor de alertas (reglas en ``docs/alertas-contrato.md``).

    Dos ejes independientes: activa/resuelta (``resolved_at``, lo decide el sistema) y
    sin leer/leída (``acknowledged``, lo decide la persona).
    """

    id: int
    sensor_id: str
    timestamp: datetime  # cuándo se abrió
    type: AlertType
    message: str
    acknowledged: bool = False
    resolved_at: Optional[datetime] = None  # nulo = sigue activa
    value: Optional[float] = None  # lectura que la abrió (nulo en OFFLINE)
    threshold: Optional[float] = None  # umbral vigente en ese momento (nulo en OFFLINE)


class AlertUpdate(BaseModel):
    """Cuerpo de ``PATCH /api/alerts/{id}``: marcar una alerta como vista (o no)."""

    acknowledged: bool


class SensorSnapshot(BaseModel):
    """Un sensor con su última lectura: cada tarjeta del dashboard."""

    sensor: Sensor
    last: Optional[Reading] = None
    status: SensorStatus = "sin_datos"


class WeatherNow(BaseModel):
    """Tiempo actual en la parcela."""

    temperature_c: float
    humidity_pct: float
    wind_kmh: float
    rain_mm: float
    description: str = ""


class WeatherHour(BaseModel):
    """Previsión para una hora concreta."""

    time: datetime
    temperature_c: float
    rain_probability_pct: float
    rain_mm: float


class Weather(BaseModel):
    """Clima real de la parcela y previsión. ``GET /api/parcels/{id}/weather``."""

    parcel_id: int
    updated_at: datetime
    current: WeatherNow
    forecast: list[WeatherHour] = Field(default_factory=list)


class Tank(BaseModel):
    """Depósito de agua. El nivel sale del último valor de su sensor ``nivel_deposito``."""

    id: int
    parcel_id: int
    name: str
    capacity_l: float
    level_sensor_id: Optional[str] = None
    level_pct: Optional[float] = None
    available_l: Optional[float] = None  # capacity_l * level_pct / 100
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class WaterShare(BaseModel):
    """Parte del agua disponible que se propone para una zona."""

    zone_id: int
    zone_name: str
    liters: float
    share_pct: float
    reason: str = ""


class WaterSummary(BaseModel):
    """Agua disponible de una parcela. ``GET /api/parcels/{id}/water``."""

    parcel_id: int
    total_capacity_l: float
    available_l: float
    level_pct: float
    tanks: list[Tank] = Field(default_factory=list)
    distribution: list[WaterShare] = Field(default_factory=list)  # propuesta de reparto


class DashboardSummary(BaseModel):
    """Respuesta de ``GET /api/dashboard``: último valor por sensor y alertas abiertas.

    ``weather`` y ``water`` son nuevos y opcionales: la interfaz actual los ignora.
    """

    parcel: Parcel
    sensors: list[SensorSnapshot] = Field(default_factory=list)
    alerts: list[Alert] = Field(default_factory=list)
    unread_alerts: int = 0
    updated_at: datetime
    weather: Optional[Weather] = None
    water: Optional[WaterSummary] = None


# --------------------------------------------------------------------------------------
# Terreno 3D
# --------------------------------------------------------------------------------------


class Zone(BaseModel):
    """Parte de una parcela: de cultivo o de no cultivo."""

    id: int
    parcel_id: int
    name: str
    type: ZoneType
    crop: Optional[str] = None
    boundary: Polygon
    area_m2: Optional[float] = None  # lo calcula el servidor a partir del contorno


class ZoneCreate(BaseModel):
    """Cuerpo de ``POST /api/parcels/{id}/zones``."""

    name: str = Field(min_length=1)
    type: ZoneType
    crop: Optional[str] = None
    boundary: Polygon


class TerrainElement(BaseModel):
    """Objeto del editor 3D: árbol, bancal o camino. Los sensores NO van aquí (ver ``Terrain.sensors``)."""

    id: int
    parcel_id: int
    type: ElementType
    subtype: Optional[str] = None  # aguacate, mango, chirimoya…
    geometry: Geometry
    height_m: Optional[float] = None


class ElementCreate(BaseModel):
    """Cuerpo de ``POST /api/parcels/{id}/elements``."""

    type: ElementType
    subtype: Optional[str] = None
    geometry: Geometry
    height_m: Optional[float] = Field(default=None, ge=0)


class BoundaryUpdate(BaseModel):
    """Cuerpo de ``PUT /api/parcels/{id}/boundary``: el contorno dibujado en el mapa."""

    boundary: Polygon


class Terrain(BaseModel):
    """Todo lo que necesita el editor 3D en una sola llamada. ``GET /api/parcels/{id}/terrain``."""

    parcel: ParcelDetail
    zones: list[Zone] = Field(default_factory=list)
    elements: list[TerrainElement] = Field(default_factory=list)
    sensors: list[Sensor] = Field(default_factory=list)
    tanks: list[Tank] = Field(default_factory=list)


# --------------------------------------------------------------------------------------
# Costes e ingresos
# --------------------------------------------------------------------------------------


class Transaction(BaseModel):
    """Movimiento económico de una parcela. El importe es siempre positivo; el signo lo da ``kind``."""

    id: int
    parcel_id: int
    kind: TransactionKind
    category: str  # agua, abono, venta…
    amount: float = Field(gt=0)  # euros
    occurred_on: date
    description: Optional[str] = None


class TransactionCreate(BaseModel):
    """Cuerpo de ``POST /api/parcels/{id}/transactions``."""

    kind: TransactionKind
    category: str = Field(min_length=1)
    amount: float = Field(gt=0)
    occurred_on: date
    description: Optional[str] = None


class Balance(BaseModel):
    """Resumen económico. ``GET /api/parcels/{id}/balance``."""

    parcel_id: int
    income: float
    expense: float
    balance: float  # income - expense
    by_category: dict[str, float] = Field(default_factory=dict)  # gastos (negativo) e ingresos (positivo)


class Health(BaseModel):
    """Respuesta de ``GET /api/health``."""

    status: Literal["ok"] = "ok"
    version: str
