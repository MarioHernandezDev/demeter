"""Datos de ejemplo para que la interfaz y el simulador avancen antes de que exista la base de datos.

NADA de esto es real ni se guarda: son datos inventados de una finca ficticia en Carchuna
(Motril), generados al vuelo y de forma determinista. Cuando existan la BD (B1) y el
repositorio (B6), cada función de este módulo se sustituye por su consulta, sin cambiar los
esquemas de ``schemas.py``.
"""

import itertools
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from demeter.api import schemas as s
from demeter.api.geo import offset, polygon_area_m2, rectangle

# Centro de la «Finca La Costa» (Carchuna, Motril) y de la «Huerta del Río».
_LAT1, _LON1 = 36.7174, -3.4301
_LAT2, _LON2 = 36.7452, -3.5101

_STEP = timedelta(minutes=1)  # un sensor envía una lectura por minuto (OFFLINE salta a los 10 min)
_HISTORY = timedelta(days=1)

_next_id = itertools.count(100)  # ids de los elementos «creados» por los endpoints de ejemplo


def new_id() -> int:
    """Id para algo recién creado (no se guarda en ningún sitio)."""
    return next(_next_id)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# --------------------------------------------------------------------------------------
# Usuarios y tokens de ejemplo
# --------------------------------------------------------------------------------------

USERS = {
    "admin": s.User(id=1, username="admin", role="admin"),
    "tecnico": s.User(id=2, username="tecnico", role="tecnico"),
    "lector": s.User(id=3, username="lector", role="lector"),
}


# --------------------------------------------------------------------------------------
# Parcelas, zonas, elementos y depósitos
# --------------------------------------------------------------------------------------


def _parcel(id: int, name: str, location: str, crop: str, lat: float, lon: float, w: float, h: float):
    boundary = rectangle(lat, lon, w, h)
    return s.ParcelDetail(
        id=id, name=name, location=location, crop=crop, latitude=lat, longitude=lon,
        area_m2=polygon_area_m2(boundary), boundary=boundary,
    )


PARCELS: dict[int, s.ParcelDetail] = {
    1: _parcel(1, "Finca La Costa", "Carchuna, Motril", "aguacate", _LAT1, _LON1, 140, 90),
    2: _parcel(2, "Huerta del Río", "Motril", "mango", _LAT2, _LON2, 100, 70),
}


def _zone(id: int, parcel_id: int, name: str, type: str, crop: Optional[str], lat, lon, w, h, dx, dy):
    boundary = rectangle(lat, lon, w, h, dx, dy)
    return s.Zone(
        id=id, parcel_id=parcel_id, name=name, type=type, crop=crop,
        boundary=boundary, area_m2=polygon_area_m2(boundary),
    )


ZONES: list[s.Zone] = [
    _zone(1, 1, "Aguacates norte", "crop", "aguacate", _LAT1, _LON1, 140, 45, 0, 22.5),
    _zone(2, 1, "Mangos suroeste", "crop", "mango", _LAT1, _LON1, 90, 45, -25, -22.5),
    _zone(3, 1, "Balsa y caminos", "no_crop", None, _LAT1, _LON1, 50, 45, 45, -22.5),
    _zone(4, 2, "Mangos", "crop", "mango", _LAT2, _LON2, 100, 70, 0, 0),
]


def _point(lat, lon, dx, dy) -> s.Geometry:
    return s.Geometry(type="Point", coordinates=offset(lat, lon, dx, dy))


ELEMENTS: list[s.TerrainElement] = [
    s.TerrainElement(id=1, parcel_id=1, type="tree", subtype="aguacate", height_m=4.5,
                     geometry=_point(_LAT1, _LON1, -40, 25)),
    s.TerrainElement(id=2, parcel_id=1, type="tree", subtype="aguacate", height_m=4.2,
                     geometry=_point(_LAT1, _LON1, -10, 25)),
    s.TerrainElement(id=3, parcel_id=1, type="tree", subtype="aguacate", height_m=4.8,
                     geometry=_point(_LAT1, _LON1, 20, 25)),
    s.TerrainElement(id=4, parcel_id=1, type="tree", subtype="mango", height_m=5.5,
                     geometry=_point(_LAT1, _LON1, -40, -20)),
    s.TerrainElement(id=5, parcel_id=1, type="tree", subtype="chirimoya", height_m=3.8,
                     geometry=_point(_LAT1, _LON1, -15, -20)),
    s.TerrainElement(
        id=6, parcel_id=1, type="terrace", subtype=None, height_m=1.2,
        geometry=s.Geometry(type="Polygon", coordinates=rectangle(_LAT1, _LON1, 60, 8, -20, 2).coordinates),
    ),
    s.TerrainElement(
        id=7, parcel_id=1, type="path", subtype=None, height_m=None,
        geometry=s.Geometry(type="LineString",
                            coordinates=[offset(_LAT1, _LON1, -65, 0), offset(_LAT1, _LON1, 65, 0)]),
    ),
    s.TerrainElement(id=8, parcel_id=2, type="tree", subtype="mango", height_m=5.0,
                     geometry=_point(_LAT2, _LON2, 0, 0)),
]

# Sensores. El nivel de un depósito es un sensor más (tipo ``nivel_deposito``).
SENSORS: list[s.Sensor] = [
    s.Sensor(id="t001", parcel_id=1, type="temperatura", unit="ºC", description="Estación norte",
             threshold_low=8, threshold_high=35, is_active=True,
             **dict(zip(("longitude", "latitude"), offset(_LAT1, _LON1, -30, 30)))),
    s.Sensor(id="h001", parcel_id=1, type="humedad_suelo", unit="%", description="Bancal 3",
             threshold_low=25, threshold_high=60,
             **dict(zip(("longitude", "latitude"), offset(_LAT1, _LON1, -20, 2)))),
    s.Sensor(id="l001", parcel_id=1, type="luminosidad", unit="klx", description="Cubierta norte",
             threshold_low=None, threshold_high=100,
             **dict(zip(("longitude", "latitude"), offset(_LAT1, _LON1, 10, 30)))),
    s.Sensor(id="a001", parcel_id=1, type="humedad_ambiente", unit="%", description="Estación norte",
             threshold_low=30, threshold_high=85,
             **dict(zip(("longitude", "latitude"), offset(_LAT1, _LON1, -30, 28)))),
    s.Sensor(id="d001", parcel_id=1, type="nivel_deposito", unit="%", description="Balsa norte",
             threshold_low=20, threshold_high=None,
             **dict(zip(("longitude", "latitude"), offset(_LAT1, _LON1, 45, -22)))),
    s.Sensor(id="d002", parcel_id=1, type="nivel_deposito", unit="%", description="Depósito sur",
             threshold_low=20, threshold_high=None,
             **dict(zip(("longitude", "latitude"), offset(_LAT1, _LON1, 55, -30)))),
    s.Sensor(id="h002", parcel_id=2, type="humedad_suelo", unit="%", description="Mangos",
             threshold_low=25, threshold_high=60,
             **dict(zip(("longitude", "latitude"), offset(_LAT2, _LON2, 0, 5)))),
]

_TANKS = [
    # (id, parcel, nombre, capacidad en litros, id del sensor de nivel, dx, dy)
    (1, 1, "Balsa norte", 20000.0, "d001", 45, -22),
    (2, 1, "Depósito sur", 5000.0, "d002", 55, -30),
]


# --------------------------------------------------------------------------------------
# Lecturas (series generadas)
# --------------------------------------------------------------------------------------


def _value(sensor_id: str, t: datetime, now: datetime) -> float:
    """Valor de ejemplo de un sensor en el instante ``t`` (curvas suaves y deterministas)."""
    hour = t.hour + t.minute / 60
    progress = 1 - (now - t) / _HISTORY  # 0 hace 24 h → 1 ahora
    if sensor_id.startswith("t"):  # temperatura: ciclo diario, máxima por la tarde
        return 22 + 6 * math.sin(2 * math.pi * (hour - 9) / 24)
    if sensor_id.startswith("a"):  # humedad ambiente: contraria a la temperatura
        return 60 - 15 * math.sin(2 * math.pi * (hour - 9) / 24)
    if sensor_id.startswith("l"):  # luminosidad: de día sí, de noche no
        return max(0.0, 80 * math.sin(math.pi * (hour - 7) / 12)) if 7 <= hour <= 19 else 0.0
    if sensor_id == "h001":  # el suelo se seca poco a poco: hoy está por debajo del umbral
        return 45 - 23 * progress
    if sensor_id == "h002":
        return 40 + 4 * math.sin(2 * math.pi * progress * 3)
    if sensor_id == "d001":  # depósitos que se vacían
        return 80 - 18 * progress
    if sensor_id == "d002":
        return 50 - 15 * progress
    return 0.0


def readings(sensor: s.Sensor) -> list[s.Reading]:
    """Últimas 24 h de lecturas, una por minuto, de la más antigua a la más reciente."""
    now = utc_now()
    last = now - timedelta(seconds=now.second)
    n = int(_HISTORY / _STEP)
    out = []
    for i in range(n, -1, -1):
        t = last - i * _STEP
        out.append(s.Reading(
            sensor_id=sensor.id, timestamp=t, value=round(_value(sensor.id, t, now), 1),
            type=sensor.type, unit=sensor.unit,
        ))
    return out


def last_reading(sensor: s.Sensor) -> Optional[s.Reading]:
    series = readings(sensor)
    return series[-1] if series else None


def compute_status(value: Optional[float], low: Optional[float], high: Optional[float]) -> str:
    """Compara un valor con los umbrales (misma regla que ``Sensor.status_for`` de la interfaz)."""
    if value is None:
        return "sin_datos"
    if low is not None and value < low:
        return "LOW"
    if high is not None and value > high:
        return "HIGH"
    return "ok"


def sensor_by_id(sensor_id: str) -> Optional[s.Sensor]:
    return next((x for x in SENSORS if x.id == sensor_id), None)


def parcel_sensors(parcel_id: int) -> list[s.Sensor]:
    return [x for x in SENSORS if x.parcel_id == parcel_id]


# --------------------------------------------------------------------------------------
# Alertas, dashboard, clima, agua y costes
# --------------------------------------------------------------------------------------


def alerts(parcel_id: Optional[int] = None) -> list[s.Alert]:
    now = utc_now()
    all_alerts = [
        s.Alert(id=1, sensor_id="h001", timestamp=now - timedelta(hours=2), type="LOW",
                message="24,2 % por debajo del umbral (25 %)", value=24.2, threshold=25.0),
        s.Alert(id=2, sensor_id="t001", timestamp=now - timedelta(days=1, hours=3), type="HIGH",
                message="36 ºC por encima del umbral (35 ºC)", value=36.0, threshold=35.0,
                acknowledged=True, resolved_at=now - timedelta(days=1, hours=1)),
        s.Alert(id=3, sensor_id="l001", timestamp=now - timedelta(hours=30), type="OFFLINE",
                message="Sin datos desde hace más de 10 min", resolved_at=now - timedelta(hours=29)),
    ]
    if parcel_id is None:
        return all_alerts
    ids = {x.id for x in parcel_sensors(parcel_id)}
    return [a for a in all_alerts if a.sensor_id in ids]


def tanks(parcel_id: int) -> list[s.Tank]:
    out = []
    for tid, pid, name, capacity, sensor_id, dx, dy in _TANKS:
        if pid != parcel_id:
            continue
        sensor = sensor_by_id(sensor_id)
        last = last_reading(sensor) if sensor else None
        pct = last.value if last else None
        lon, lat = offset(PARCELS[pid].latitude, PARCELS[pid].longitude, dx, dy)
        out.append(s.Tank(
            id=tid, parcel_id=pid, name=name, capacity_l=capacity, level_sensor_id=sensor_id,
            level_pct=pct, available_l=round(capacity * pct / 100, 1) if pct is not None else None,
            latitude=lat, longitude=lon,
        ))
    return out


def water(parcel_id: int) -> s.WaterSummary:
    ts = tanks(parcel_id)
    capacity = sum(t.capacity_l for t in ts)
    available = round(sum(t.available_l or 0 for t in ts), 1)
    crop_zones = [z for z in ZONES if z.parcel_id == parcel_id and z.type == "crop"]
    crop_area = sum(z.area_m2 or 0 for z in crop_zones)
    # Reparto de EJEMPLO, proporcional a la superficie de cultivo. El algoritmo real es el
    # recomendador de riego (E5, #7).
    shares = [
        s.WaterShare(
            zone_id=z.id, zone_name=z.name, liters=round(available * (z.area_m2 or 0) / crop_area, 1),
            share_pct=round(100 * (z.area_m2 or 0) / crop_area, 1),
            reason="Proporcional a la superficie de cultivo (m²)",
        )
        for z in crop_zones
    ] if crop_area else []
    return s.WaterSummary(
        parcel_id=parcel_id, total_capacity_l=capacity, available_l=available,
        level_pct=round(100 * available / capacity, 1) if capacity else 0.0,
        tanks=ts, distribution=shares,
    )


def weather(parcel_id: int) -> s.Weather:
    now = utc_now()
    top = now.replace(minute=0, second=0)
    forecast = []
    for h in range(1, 25):
        t = top + timedelta(hours=h)
        prob = min(95.0, 5 + 3.5 * h)  # va subiendo: mañana es probable que llueva
        forecast.append(s.WeatherHour(
            time=t, temperature_c=round(21 + 5 * math.sin(2 * math.pi * (t.hour - 9) / 24), 1),
            rain_probability_pct=round(prob, 0), rain_mm=round(max(0.0, (prob - 60) / 20), 1),
        ))
    return s.Weather(
        parcel_id=parcel_id, updated_at=now,
        current=s.WeatherNow(temperature_c=round(_value("t001", now, now), 1), humidity_pct=58.0,
                             wind_kmh=11.0, rain_mm=0.0, description="Parcialmente nublado"),
        forecast=forecast,
    )


def prediction(sensor: s.Sensor) -> Optional[s.SensorPrediction]:
    """Predicción de EJEMPLO a 24 h: prolonga la curva del sensor con una banda que se ensancha.

    El modelo real es el de predicción (E4). Aquí solo importa la forma de la respuesta.
    """
    last = last_reading(sensor)
    if last is None:
        return None
    now = utc_now()
    top = now.replace(minute=0, second=0)
    points = []
    for h in range(1, 25):
        t = top + timedelta(hours=h)
        v = _value(sensor.id, t, now)
        m = 0.5 + 0.15 * h  # la incertidumbre crece con el tiempo
        lo, hi = v - m, v + m
        if sensor.unit == "%":
            v, lo, hi = (min(100.0, max(0.0, x)) for x in (v, lo, hi))
        points.append(s.PredictionPoint(time=t, value=round(v, 1), lower=round(lo, 1), upper=round(hi, 1)))
    crossing = None
    if compute_status(last.value, sensor.threshold_low, sensor.threshold_high) == "ok":
        for p in points:
            st = compute_status(p.value, sensor.threshold_low, sensor.threshold_high)
            if st != "ok":
                crossing = s.ThresholdCrossing(type=st, at=p.time, value=p.value)
                break
    delta = points[-1].value - points[0].value
    span = (sensor.threshold_high - sensor.threshold_low) if None not in (
        sensor.threshold_low, sensor.threshold_high) else max(abs(points[0].value), 1.0)
    trend = "stable" if abs(delta) < 0.05 * span else ("rising" if delta > 0 else "falling")
    return s.SensorPrediction(
        sensor_id=sensor.id, type=sensor.type, unit=sensor.unit, generated_at=now,
        model="ejemplo-v0", trend=trend, crossing=crossing, points=points,
    )


def irrigation(parcel_id: int) -> s.IrrigationAdvice:
    """Consejo de riego de EJEMPLO con una regla simple. El algoritmo real es el de E5 (#7)."""
    now = utc_now()
    w, wx = water(parcel_id), weather(parcel_id)
    soil = [x for x in parcel_sensors(parcel_id) if x.type == "humedad_suelo"]
    values = [r.value for r in (last_reading(x) for x in soil) if r is not None]
    soil_pct = round(sum(values) / len(values), 1) if values else None
    low = min((x.threshold_low for x in soil if x.threshold_low is not None), default=None)
    rain_mm = round(sum(f.rain_mm for f in wx.forecast), 1)
    factors = s.IrrigationFactors(
        soil_moisture_pct=soil_pct,
        rain_probability_pct=max((f.rain_probability_pct for f in wx.forecast), default=None),
        rain_mm_24h=rain_mm, tank_level_pct=w.level_pct,
    )

    def advice(action, summary, zones=(), total=0.0):
        return s.IrrigationAdvice(
            parcel_id=parcel_id, generated_at=now, action=action, summary=summary,
            total_liters=total, available_l=w.available_l, enough_water=w.available_l >= total,
            factors=factors, zones=list(zones),
        )

    if soil_pct is None or low is None or soil_pct >= low + 5:
        return advice("wait", "El suelo aún tiene humedad suficiente. No hace falta regar hoy.")
    if rain_mm >= 5:
        return advice("skip", f"Se esperan {rain_mm} mm de lluvia en 24 h. Mejor no regar.")
    start = (now + timedelta(days=1)).replace(hour=5, minute=0, second=0) if now.hour >= 5 else now.replace(hour=5, minute=0, second=0)
    crop = [z for z in ZONES if z.parcel_id == parcel_id and z.type == "crop"]
    need = {z.id: 2.0 * (z.area_m2 or 0) for z in crop}  # 2 L/m² de ejemplo
    scale = min(1.0, w.available_l / sum(need.values())) if need and sum(need.values()) else 0.0
    zones = [
        s.IrrigationZone(
            zone_id=z.id, zone_name=z.name, liters=round(need[z.id] * scale, 1), start_at=start,
            duration_min=max(1, round(need[z.id] * scale / 300)),  # caudal de ejemplo: 300 L/min
            reason=f"Suelo al {soil_pct} %, por debajo de lo recomendado",
        )
        for z in crop
    ]
    total = round(sum(z.liters for z in zones), 1)
    return advice("irrigate", f"Regar {total:.0f} L repartidos en {len(zones)} zonas, a primera hora.",
                  zones, total)


def transactions(parcel_id: int) -> list[s.Transaction]:
    rows = [
        (1, "income", "venta", 1850.00, date(2026, 10, 28), "Venta de aguacate, 1.ª partida"),
        (2, "expense", "agua", 126.40, date(2026, 10, 31), "Recibo de agua de octubre"),
        (3, "expense", "abono", 310.00, date(2026, 11, 3), None),
        (4, "expense", "agua", 98.75, date(2026, 11, 9), "Recarga de la balsa"),
        (5, "income", "venta", 920.00, date(2026, 11, 12), "Venta de aguacate, 2.ª partida"),
    ]
    if parcel_id != 1:
        return []
    return [s.Transaction(id=i, parcel_id=1, kind=k, category=c, amount=a, occurred_on=d, description=desc)
            for i, k, c, a, d, desc in rows]


def balance(parcel_id: int) -> s.Balance:
    income = expense = 0.0
    by_category: dict[str, float] = {}
    for t in transactions(parcel_id):
        signed = t.amount if t.kind == "income" else -t.amount
        by_category[t.category] = round(by_category.get(t.category, 0.0) + signed, 2)
        if t.kind == "income":
            income += t.amount
        else:
            expense += t.amount
    return s.Balance(parcel_id=parcel_id, income=round(income, 2), expense=round(expense, 2),
                     balance=round(income - expense, 2), by_category=by_category)
