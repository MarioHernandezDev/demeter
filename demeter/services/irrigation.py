"""Recomendador de riego (E5, issue #7) y reparto del agua de los depósitos (idea #56).

Decide si hay que regar cada parcela, cuánta agua (litros) necesita cada zona de cultivo y a
qué hora empezar. Devuelve el JSON acordado en ``docs/insights-contrato.md`` (sección 2).

Cómo se calcula (todo explicable al agricultor):

1. **Humedad del suelo** de cada zona: la media de los sensores ``humedad_suelo`` que caen
   dentro de su contorno; si una zona no tiene sensor, la media de la parcela.
2. **¿Hace falta regar?** Una zona pide agua cuando su suelo baja del umbral bajo más un
   15 % del rango entre umbrales (con 25–60 % riega por debajo de 30,3 %). Si ninguna lo pide → ``wait``.
3. **¿Va a llover?** Si la probabilidad de lluvia en 24 h llega al 70 % y la lluvia útil
   prevista (80 % de la que cae) cubre al menos el 60 % de lo que pedirían las zonas → ``skip``.
4. **Cuánta agua**: lo que consumirá el cultivo en un día (ETc = Kc · ET0, con ET0 de
   Hargreaves a partir de la temperatura prevista), aumentado hasta el doble cuanto más seco
   está el suelo, menos la lluvia útil. En L/m² (1 mm = 1 L/m²) por la superficie de la zona.
5. **Cuándo**: la hora más fresca entre las 5 y las 8 de la mañana (hora local), para que se
   evapore menos. Las zonas se riegan una detrás de otra con el caudal de la bomba.
6. **Si no hay agua para todo**, el reparto se recorta en proporción y se dice en el resumen.
   Nunca se pide más agua de la que hay en los depósitos.

Todo son funciones puras: reciben los datos y la hora y no tocan la base de datos.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Optional
from zoneinfo import ZoneInfo

from demeter.api import schemas as s

LOCAL_TZ = ZoneInfo("Europe/Madrid")

# Coeficiente de cultivo (Kc, FAO-56, valores medios para la Costa Tropical).
CROP_KC = {
    "aguacate": 0.75,
    "mango": 0.70,
    "chirimoya": 0.80,
    "tomate": 1.05,
}
DEFAULT_KC = 0.80

TRIGGER_FRACTION = 0.15  # se riega por debajo de umbral bajo + 15 % del rango
TARGET_FRACTION = 0.60  # humedad «cómoda»: umbral bajo + 60 % del rango
MAX_DRY_BOOST = 1.0  # con el suelo en el umbral bajo se da hasta el doble de la ETc
RAIN_EFFICIENCY = 0.8  # parte de la lluvia que aprovecha el suelo
SKIP_RAIN_PROBABILITY = 70.0  # %
SKIP_RAIN_COVERAGE = 0.6  # la lluvia útil cubre al menos el 60 % de lo necesario
DEFAULT_FLOW_L_MIN = 300.0  # caudal de la bomba (L/min) si la parcela no dice otro
BEST_HOURS_LOCAL = range(5, 9)  # 5:00 a 8:00, hora local
DEFAULT_LATITUDE = 36.7  # Motril
DEFAULT_TEMPS = (12.0, 22.0)  # mínima y máxima si no hay previsión (noviembre en la costa)


def utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


# ------------------------------------------------------------------ evapotranspiración


def extraterrestrial_radiation_mm(latitude: float, day_of_year: int) -> float:
    """Radiación solar en lo alto de la atmósfera (Ra, FAO-56 ec. 21), en mm/día de agua."""
    phi = math.radians(latitude)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta))))
    ra_mj = (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.sin(ws)
    )
    return 0.408 * ra_mj


def et0_hargreaves(t_min: float, t_max: float, latitude: float, day_of_year: int) -> float:
    """Evapotranspiración de referencia (mm/día) solo con temperaturas (Hargreaves-Samani)."""
    t_mean = (t_min + t_max) / 2
    ra = extraterrestrial_radiation_mm(latitude, day_of_year)
    return max(0.0, 0.0023 * ra * (t_mean + 17.8) * math.sqrt(max(0.0, t_max - t_min)))


def crop_kc(crop: Optional[str]) -> float:
    return CROP_KC.get((crop or "").strip().lower(), DEFAULT_KC)


# ------------------------------------------------------------------ geometría


def point_in_polygon(lon: float, lat: float, polygon: s.Polygon) -> bool:
    """¿Está el punto dentro del anillo exterior? (rayo hacia el este)."""
    ring = polygon.coordinates[0]
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > lat) != (y2 > lat):
            x = x1 + (lat - y1) * (x2 - x1) / (y2 - y1)
            if x > lon:
                inside = not inside
    return inside


# ------------------------------------------------------------------ reparto del agua (#56)


@dataclass(frozen=True)
class WaterPlan:
    """Una forma de repartir el agua disponible entre zonas."""

    criterion: str  # "superficie", "cultivo" o "necesidad"
    description: str
    liters: dict[int, float]  # zone_id -> litros


def available_water(tanks: Iterable[s.Tank]) -> tuple[float, Optional[float]]:
    """Agua disponible sumando todos los depósitos y nivel medio ponderado (o ``None``)."""
    tanks = list(tanks)
    known = [t for t in tanks if t.available_l is not None]
    available = round(sum(t.available_l for t in known), 1)
    capacity = sum(t.capacity_l for t in known)
    return available, (round(100 * available / capacity, 1) if capacity else None)


def split_water(
    weights: dict[int, float], available_l: float, cap: Optional[dict[int, float]] = None
) -> dict[int, float]:
    """Reparte ``available_l`` en proporción a ``weights``. Con ``cap`` nadie recibe más de su tope
    (lo que sobra va a las demás); nunca se reparte más de lo disponible."""
    result = {z: 0.0 for z in weights}
    pending = {z: w for z, w in weights.items() if w > 0}
    left = max(0.0, available_l)
    while pending and left > 1e-9:
        total = sum(pending.values())
        share = {z: left * w / total for z, w in pending.items()}
        if cap is None:
            for z, v in share.items():
                result[z] += v
            break
        full = {z for z, v in share.items() if result[z] + v >= cap[z]}
        if not full:
            for z, v in share.items():
                result[z] += v
            break
        for z in full:
            left -= cap[z] - result[z]
            result[z] = cap[z]
            del pending[z]
    return {z: round(v, 1) for z, v in result.items()}


def distribution_options(
    zones: Iterable[s.Zone], available_l: float, needs_l: Optional[dict[int, float]] = None
) -> list[WaterPlan]:
    """Varias formas razonables de repartir el agua entre las zonas de cultivo (idea #56).

    - ``superficie``: proporcional a los m² de cada zona.
    - ``cultivo``: proporcional a m² × Kc (los cultivos que más beben reciben más).
    - ``necesidad``: lo que pide cada zona según el recomendador (``needs_l``), sin pasarse; si
      sobra agua se queda en el depósito.
    """
    crop = [z for z in zones if z.type == "crop" and (z.area_m2 or 0) > 0]
    plans = [
        WaterPlan("superficie", "Proporcional a la superficie de cada zona (m²)",
                  split_water({z.id: z.area_m2 for z in crop}, available_l)),
        WaterPlan("cultivo", "Proporcional a la superficie y a lo que bebe cada cultivo (m² × Kc)",
                  split_water({z.id: z.area_m2 * crop_kc(z.crop) for z in crop}, available_l)),
    ]
    if needs_l is not None:
        need = {z.id: needs_l.get(z.id, 0.0) for z in crop}
        budget = min(available_l, sum(need.values()))
        plans.append(WaterPlan("necesidad", "Lo que pide cada zona según su suelo y el tiempo",
                               split_water(need, budget, cap=need)))
    return plans


# ------------------------------------------------------------------ recomendador (#7)


def _fmt(x: float) -> str:
    """Número a la española para las frases: 14150 → «14 150», 22.0 → «22»."""
    if abs(x - round(x)) < 0.05:
        return f"{round(x):,}".replace(",", " ")
    return f"{x:.1f}".replace(".", ",")


def best_start(now: datetime, forecast: list[s.WeatherHour]) -> datetime:
    """Hora más fresca entre las 5 y las 8 (hora local) que todavía no haya pasado."""
    now = utc(now)
    temps = {utc(h.time).replace(minute=0, second=0, microsecond=0): h.temperature_c for h in forecast}
    local_now = now.astimezone(LOCAL_TZ)
    for day in (0, 1):
        base = (local_now + timedelta(days=day)).replace(minute=0, second=0, microsecond=0)
        candidates = [base.replace(hour=h).astimezone(timezone.utc) for h in BEST_HOURS_LOCAL]
        candidates = [c for c in candidates if c > now]
        if candidates:
            known = [c for c in candidates if c in temps]
            if known:
                return min(known, key=lambda c: (temps[c], c))
            return candidates[min(1, len(candidates) - 1)]  # sin previsión: a las 6 si se puede
    raise AssertionError("siempre hay una franja mañana")


def _zone_moisture(zone: s.Zone, soil: list[tuple[s.Sensor, float]], parcel_mean: Optional[float]) -> Optional[float]:
    inside = [v for x, v in soil if x.latitude is not None and x.longitude is not None
              and point_in_polygon(x.longitude, x.latitude, zone.boundary)]
    return round(fmean(inside), 1) if inside else parcel_mean


def recommend(
    parcel_id: int,
    zones: Iterable[s.Zone],
    soil: Iterable[tuple[s.Sensor, Optional[float]]],
    forecast: list[s.WeatherHour],
    tanks: Iterable[s.Tank],
    now: datetime,
    *,
    latitude: Optional[float] = None,
    flow_l_min: float = DEFAULT_FLOW_L_MIN,
) -> s.IrrigationAdvice:
    """Consejo de riego de una parcela con la forma del contrato.

    ``soil``: cada sensor ``humedad_suelo`` de la parcela con su último valor (``None`` si no tiene).
    ``forecast``: previsión horaria de las próximas 24 h (``GET /api/parcels/{id}/weather``).
    """
    now = utc(now)
    zones = [z for z in zones if z.type == "crop"]
    soil = [(x, v) for x, v in soil if x.type == "humedad_suelo" and v is not None]
    available_l, tank_pct = available_water(tanks)

    soil_mean = round(fmean(v for _, v in soil), 1) if soil else None
    rain_prob = max((h.rain_probability_pct for h in forecast), default=None)
    rain_mm = round(sum(h.rain_mm for h in forecast), 1) if forecast else None
    factors = s.IrrigationFactors(
        soil_moisture_pct=soil_mean, rain_probability_pct=rain_prob, rain_mm_24h=rain_mm,
        tank_level_pct=tank_pct,
    )

    def advice(action: str, summary: str, plan: list[s.IrrigationZone] = ()) -> s.IrrigationAdvice:
        total = round(sum(z.liters for z in plan), 1)
        return s.IrrigationAdvice(
            parcel_id=parcel_id, generated_at=now, action=action, summary=summary,
            total_liters=total, available_l=available_l, enough_water=available_l >= total,
            factors=factors, zones=list(plan),
        )

    # Umbrales de humedad: los de los sensores (el más exigente).
    lows = [x.threshold_low for x, _ in soil if x.threshold_low is not None]
    highs = [x.threshold_high for x, _ in soil if x.threshold_high is not None]
    if soil_mean is None or not lows:
        return advice("wait", "No hay datos de humedad del suelo: no se puede recomendar riego todavía.")
    if not zones:
        return advice("wait", "La parcela no tiene zonas de cultivo dibujadas: no hay nada que regar.")
    if not forecast:
        return advice("wait", "No hay previsión del tiempo: se vuelve a mirar cuando llegue.")
    low = max(lows)
    high = min(highs) if highs and min(highs) > low else low + 35
    trigger = low + TRIGGER_FRACTION * (high - low)
    target = low + TARGET_FRACTION * (high - low)

    # ¿Qué zonas lo piden?
    moisture = {z.id: _zone_moisture(z, soil, soil_mean) for z in zones}
    dry = [z for z in zones if moisture[z.id] is not None and moisture[z.id] < trigger]
    if not dry:
        return advice("wait", f"El suelo está al {_fmt(soil_mean)} %, con humedad suficiente. "
                              "No hace falta regar hoy.")

    # Necesidad en L/m²: ETc de un día, más cuanto más seco, menos la lluvia útil.
    temps = [h.temperature_c for h in forecast]
    t_min, t_max = (min(temps), max(temps)) if temps else DEFAULT_TEMPS
    doy = now.astimezone(LOCAL_TZ).timetuple().tm_yday
    et0 = et0_hargreaves(t_min, t_max, latitude if latitude is not None else DEFAULT_LATITUDE, doy)
    useful_rain = RAIN_EFFICIENCY * (rain_mm or 0.0)

    gross_mm, need_l = {}, {}
    for z in dry:
        dryness = min(1.0, max(0.0, (target - moisture[z.id]) / (target - low)))
        gross_mm[z.id] = crop_kc(z.crop) * et0 * (1 + MAX_DRY_BOOST * dryness)
        need_l[z.id] = max(0.0, gross_mm[z.id] - useful_rain) * (z.area_m2 or 0)

    # Lluvia probable que cubre casi todo → no regar (idea #55).
    if (rain_prob or 0) >= SKIP_RAIN_PROBABILITY and useful_rain >= SKIP_RAIN_COVERAGE * max(gross_mm.values()):
        return advice("skip", f"Lluvia muy probable ({_fmt(rain_prob)} %, unos {_fmt(rain_mm)} mm en 24 h): "
                              "no hace falta regar, la lluvia cubrirá lo que necesita el suelo.")
    if sum(need_l.values()) < 1:
        return advice("skip", f"Se esperan {_fmt(rain_mm)} mm de lluvia en 24 h, suficiente para el suelo. "
                              "Mejor no regar.")
    if available_l <= 0:
        return advice("wait", "Haría falta regar, pero los depósitos están vacíos o sin dato de nivel. "
                              "Revisa el agua disponible.")

    # Reparto: lo que pide cada zona, recortado en proporción si no alcanza.
    needed_total = sum(need_l.values())
    liters = split_water(need_l, min(available_l, needed_total), cap=need_l)
    short = available_l < needed_total - 0.5

    start = best_start(now, forecast)
    plan, t = [], start
    for z in dry:
        if liters[z.id] <= 0:
            continue
        minutes = max(1, math.ceil(liters[z.id] / flow_l_min))
        reason = (f"Suelo al {_fmt(moisture[z.id])} %, por debajo de lo recomendado ({_fmt(trigger)} %). "
                  f"{_fmt(liters[z.id] / z.area_m2)} L/m² para {z.crop or 'el cultivo'}")
        plan.append(s.IrrigationZone(zone_id=z.id, zone_name=z.name, liters=liters[z.id], start_at=t,
                                     duration_min=minutes, reason=reason))
        t += timedelta(minutes=minutes)

    total = sum(p.liters for p in plan)
    hour = start.astimezone(LOCAL_TZ).strftime("%H:%M")
    zonas = "1 zona" if len(plan) == 1 else f"{len(plan)} zonas"
    summary = f"Regar {_fmt(total)} L repartidos en {zonas}, empezando a las {hour}."
    if short:
        summary += (f" Harían falta {_fmt(needed_total)} L, pero solo hay {_fmt(available_l)} L en los "
                    "depósitos: el reparto se ha recortado.")
    if useful_rain > 0:
        summary += f" Ya descuenta {_fmt(rain_mm)} mm de lluvia prevista."
    return advice("irrigate", summary, plan)
