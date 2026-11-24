"""Motor de predicción a 24 h (E4, issue #5).

Prevé las próximas 24 horas de un sensor a partir de sus lecturas recientes y devuelve el JSON
acordado en ``docs/insights-contrato.md`` (sección 1): 24 puntos horarios con banda de
confianza, la tendencia y el primer cruce de umbral previsto.

Dos modelos sencillos y explicables, según cómo se comporta cada magnitud:

- **Ciclo diario** (temperatura, humedad ambiente, luminosidad): lo que pasó ayer a esa hora,
  corregido por cuánto se diferencia hoy de ayer. La corrección se va apagando con las horas.
  Necesita unas 20 h de historia; si no las hay, se usa el modelo de tendencia.
- **Tendencia** (humedad del suelo, nivel de depósito y el resto): recta de mínimos cuadrados
  sobre las últimas 6 h, prolongada hacia delante. Es lo que hace el suelo al secarse o un
  depósito al vaciarse.

La banda de confianza sale del error del propio modelo sobre el pasado reciente (con un mínimo
para que nunca sea una línea) y se ensancha con la raíz de las horas de distancia.

Todo son funciones puras: reciben las lecturas y la hora actual y no tocan la base de datos, así
se pueden probar sin montar nada. Quien llama (la API) decide de dónde salen las lecturas.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import fmean, pstdev
from typing import Optional

from demeter.api import schemas as s

HORIZON_HOURS = 24
STEP = timedelta(hours=1)

MODEL_DAILY = "ciclo-diario-v1"
MODEL_TREND = "tendencia-lineal-v1"

# Magnitudes que repiten un ciclo cada día (sol, temperatura). El resto se predice por tendencia.
DAILY_TYPES = {"temperatura", "humedad_ambiente", "luminosidad"}

MIN_HOURS = 3  # horas distintas con lecturas que hacen falta para predecir algo
MIN_HOURS_DAILY = 20  # historia mínima para fiarse del ciclo de ayer
TREND_WINDOW = 6  # horas que mira la recta de tendencia
MAX_SILENCE = timedelta(hours=3)  # si la última lectura es más vieja, no se predice
OFFSET_FADE_HOURS = 12.0  # a qué ritmo se olvida la diferencia «hoy frente a ayer»
Z_80 = 1.28  # banda del 80 %
STABLE_FRACTION = 0.05  # «stable» si cambia menos del 5 % del rango (contrato, sección 1)


@dataclass(frozen=True)
class Point:
    time: datetime
    value: float
    lower: float
    upper: float


# ------------------------------------------------------------------ utilidades


def utc(dt: datetime) -> datetime:
    """Fecha en UTC con zona. Sin zona se entiende UTC (así se guarda todo)."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def floor_hour(dt: datetime) -> datetime:
    return utc(dt).replace(minute=0, second=0, microsecond=0)


def nearest_hour(dt: datetime) -> datetime:
    return floor_hour(utc(dt) + STEP / 2)


def hourly_means(readings: Iterable[tuple[datetime, float]]) -> dict[datetime, float]:
    """Media de las lecturas alrededor de cada hora en punto (de y-30 min a y+29 min, UTC).

    Se agrupa por la hora más cercana, no por la hora truncada, para que la media represente de
    verdad ese instante y la curva prevista no salga desplazada media hora.
    Ordenado de la más antigua a la última.
    """
    buckets: dict[datetime, list[float]] = {}
    for t, v in readings:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        buckets.setdefault(nearest_hour(t), []).append(float(v))
    return {h: fmean(vs) for h, vs in sorted(buckets.items())}


def _linear_fit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """Recta de mínimos cuadrados ``y = a + b·x``. Devuelve ``(a, b)``."""
    mx, my = fmean(xs), fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return my, 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


def _scale(low: Optional[float], high: Optional[float], ref: float) -> float:
    """Tamaño «natural» de la magnitud: el rango entre umbrales o, si falta uno, el propio valor."""
    if low is not None and high is not None and high > low:
        return high - low
    return max(abs(ref), 1.0)


# ------------------------------------------------------------------ modelos


def _trend_model(hours: dict[datetime, float], top: datetime) -> tuple[list[float], float]:
    """Prolonga la recta de las últimas ``TREND_WINDOW`` horas. Devuelve (valores, sigma)."""
    recent = list(hours.items())[-TREND_WINDOW:]
    xs = [(h - top) / STEP for h, _ in recent]  # horas respecto a la hora en punto actual
    ys = [v for _, v in recent]
    a, b = _linear_fit(xs, ys)
    residuals = [y - (a + b * x) for x, y in zip(xs, ys)]
    sigma = pstdev(residuals) if len(residuals) > 2 else 0.0
    return [a + b * h for h in range(1, HORIZON_HOURS + 1)], sigma


def _daily_model(hours: dict[datetime, float], top: datetime) -> tuple[list[float], float]:
    """Lo de ayer a la misma hora más la diferencia actual frente a ayer, que se va apagando."""
    # Diferencia hoy-ayer con las últimas 3 horas que tengan pareja hace 24 h.
    pairs = [(v, hours[h - timedelta(days=1)]) for h, v in list(hours.items())[-3:]
             if h - timedelta(days=1) in hours]
    offset = fmean(today - yesterday for today, yesterday in pairs) if pairs else 0.0

    # Error del modelo «igual que ayer» sobre el último día: da el ancho de la banda.
    errors = [v - hours[h - timedelta(days=1)] - offset for h, v in hours.items()
              if h - timedelta(days=1) in hours]
    sigma = pstdev(errors) if len(errors) > 2 else 0.0

    by_hour_of_day: dict[int, list[float]] = {}
    for h, v in hours.items():
        by_hour_of_day.setdefault(h.hour, []).append(v)

    values = []
    for k in range(1, HORIZON_HOURS + 1):
        t = top + k * STEP
        base = hours.get(t - timedelta(days=1))
        if base is None:  # hueco en la historia: media de esa hora en los días que haya
            same = by_hour_of_day.get(t.hour)
            base = fmean(same) if same else list(hours.values())[-1]
        values.append(base + offset * math.exp(-k / OFFSET_FADE_HOURS))
    return values, sigma


# ------------------------------------------------------------------ predicción


def forecast(
    readings: Iterable[tuple[datetime, float]],
    now: datetime,
    *,
    daily: bool,
    low: Optional[float] = None,
    high: Optional[float] = None,
    clamp: Optional[tuple[float, float]] = None,
) -> Optional[tuple[str, list[Point]]]:
    """Prevé las próximas 24 h. Devuelve ``(modelo, puntos)`` o ``None`` si no hay datos.

    ``readings``: pares ``(fecha, valor)`` en cualquier orden. Solo cuentan los anteriores a ``now``.
    ``daily``: usar el modelo de ciclo diario si hay historia suficiente.
    ``low``/``high``: umbrales, solo para dar escala a la banda mínima.
    ``clamp``: límites físicos (p. ej. ``(0, 100)`` en porcentajes).
    """
    now = utc(now)
    hours = hourly_means((t, v) for t, v in readings if utc(t) <= now)
    if len(hours) < MIN_HOURS:
        return None
    last_hour = next(reversed(hours))
    if now - last_hour > MAX_SILENCE + STEP:
        return None  # el sensor lleva horas callado: eso es una alerta OFFLINE, no una predicción

    top = floor_hour(now)
    span_hours = (last_hour - next(iter(hours))) / STEP
    if daily and span_hours >= MIN_HOURS_DAILY:
        model, (values, sigma) = MODEL_DAILY, _daily_model(hours, top)
    else:
        model, (values, sigma) = MODEL_TREND, _trend_model(hours, top)

    # Banda mínima: un 2 % de la escala de la magnitud, para no prometer exactitud.
    sigma = max(sigma, 0.02 * _scale(low, high, hours[last_hour]))
    points = []
    for k, v in enumerate(values, start=1):
        half = Z_80 * sigma * math.sqrt(k)
        lo, hi = v - half, v + half
        if clamp is not None:
            v, lo, hi = (min(clamp[1], max(clamp[0], x)) for x in (v, lo, hi))
        points.append(Point(top + k * STEP, round(v, 1), round(lo, 1), round(hi, 1)))
    return model, points


def status(value: float, low: Optional[float], high: Optional[float]) -> Optional[str]:
    """``LOW``/``HIGH`` si el valor está fuera de umbral; ``None`` si está dentro."""
    if low is not None and value < low:
        return "LOW"
    if high is not None and value > high:
        return "HIGH"
    return None


def trend_of(points: list[Point], low: Optional[float], high: Optional[float]) -> str:
    """``rising``/``falling``/``stable`` comparando el último punto con el primero (contrato)."""
    delta = points[-1].value - points[0].value
    if abs(delta) < STABLE_FRACTION * _scale(low, high, points[0].value):
        return "stable"
    return "rising" if delta > 0 else "falling"


def first_crossing(
    points: list[Point], current: float, low: Optional[float], high: Optional[float]
) -> Optional[tuple[str, Point]]:
    """Primer punto previsto fuera de umbral. ``None`` si no sale o si ya está fuera ahora
    (eso ya lo avisa la alerta activa)."""
    if status(current, low, high) is not None:
        return None
    for p in points:
        st = status(p.value, low, high)
        if st is not None:
            return st, p
    return None


def predict_sensor(
    sensor: s.Sensor, readings: Iterable[tuple[datetime, float]], now: datetime
) -> Optional[s.SensorPrediction]:
    """Predicción de un sensor con la forma del contrato. ``None`` = sin datos suficientes (404)."""
    now = utc(now)
    series = sorted(((utc(t), v) for t, v in readings if utc(t) <= now), key=lambda r: r[0])
    result = forecast(
        series, now,
        daily=sensor.type in DAILY_TYPES,
        low=sensor.threshold_low, high=sensor.threshold_high,
        clamp=(0.0, 100.0) if sensor.unit == "%" else ((0.0, math.inf) if sensor.type == "luminosidad" else None),
    )
    if result is None:
        return None
    model, points = result
    low, high = sensor.threshold_low, sensor.threshold_high
    crossing = first_crossing(points, series[-1][1], low, high)
    return s.SensorPrediction(
        sensor_id=sensor.id, type=sensor.type, unit=sensor.unit, generated_at=now,
        horizon_hours=HORIZON_HOURS, step_minutes=int(STEP.total_seconds() // 60), model=model,
        trend=trend_of(points, low, high),
        crossing=s.ThresholdCrossing(type=crossing[0], at=crossing[1].time, value=crossing[1].value)
        if crossing else None,
        points=[s.PredictionPoint(time=p.time, value=p.value, lower=p.lower, upper=p.upper) for p in points],
    )
