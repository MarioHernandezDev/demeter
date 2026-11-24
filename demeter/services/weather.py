"""Clima real de una parcela con Open-Meteo (idea ``api-clima``).

Open-Meteo es gratuito y no pide clave. Se le pasan las coordenadas de la parcela y devuelve el
tiempo actual y la previsión por horas. Lo que se hace aquí:

- Se guarda la respuesta en memoria ``CACHE_TTL`` (10 min): el dashboard se refresca cada pocos
  segundos y no hay que llamar fuera cada vez.
- Si la llamada falla (sin internet, servicio caído), se sigue usando lo último que se tuvo hasta
  ``STALE_MAX`` (6 h), marcado con ``stale=True``. Si no hay nada, ``get_weather`` devuelve
  ``None`` y la API lo dice con claridad: **nunca se inventa un clima**.
- Tras un fallo no se reintenta hasta pasados ``RETRY_AFTER`` (60 s), para que un dashboard sin
  internet no se quede esperando cada vez.

Solo salen hacia Open-Meteo las coordenadas (redondeadas a 2 decimales, unos 1,1 km) de la parcela.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from demeter.api import schemas as s

log = logging.getLogger(__name__)

BASE_URL = os.environ.get("DEMETER_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
CACHE_TTL = timedelta(minutes=10)
STALE_MAX = timedelta(hours=6)
RETRY_AFTER = timedelta(seconds=60)
TIMEOUT_SECONDS = 5
FORECAST_HOURS = 24

# Códigos de tiempo de la OMM (WMO) que usa Open-Meteo, en español.
_WMO = {
    0: "Despejado", 1: "Mayormente despejado", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Niebla", 48: "Niebla con escarcha",
    51: "Llovizna ligera", 53: "Llovizna", 55: "Llovizna intensa",
    56: "Llovizna helada", 57: "Llovizna helada intensa",
    61: "Lluvia ligera", 63: "Lluvia", 65: "Lluvia intensa",
    66: "Lluvia helada", 67: "Lluvia helada intensa",
    71: "Nieve ligera", 73: "Nieve", 75: "Nieve intensa", 77: "Granos de nieve",
    80: "Chubascos ligeros", 81: "Chubascos", 82: "Chubascos violentos",
    85: "Chubascos de nieve", 86: "Chubascos de nieve intensos",
    95: "Tormenta", 96: "Tormenta con granizo", 99: "Tormenta con granizo fuerte",
}

_lock = threading.Lock()
_cache: dict[tuple[float, float], tuple[datetime, s.Weather]] = {}
_failed_at: dict[tuple[float, float], datetime] = {}


def describe(code: Optional[int]) -> str:
    return _WMO.get(code, "") if code is not None else ""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fetch_json(latitude: float, longitude: float) -> dict:
    """La llamada a Open-Meteo. Aparte para poder sustituirla en las pruebas."""
    query = urllib.parse.urlencode({
        "latitude": latitude, "longitude": longitude, "timezone": "UTC", "forecast_days": 3,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code",
        "hourly": "temperature_2m,precipitation_probability,precipitation",
    })
    request = urllib.request.Request(f"{BASE_URL}?{query}", headers={"User-Agent": "demeter-api"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def parse(parcel_id: int, data: dict, now: datetime) -> s.Weather:
    """Convierte la respuesta de Open-Meteo en ``Weather``. Lanza ``ValueError`` si no es válida."""
    try:
        cur = data["current"]
        hourly = data["hourly"]
        current = s.WeatherNow(
            temperature_c=float(cur["temperature_2m"]),
            humidity_pct=float(cur["relative_humidity_2m"]),
            wind_kmh=float(cur["wind_speed_10m"]),
            rain_mm=float(cur.get("precipitation") or 0.0),
            description=describe(cur.get("weather_code")),
        )
        forecast = []
        for i, text in enumerate(hourly["time"]):
            when = _utc(text)
            if when <= now:
                continue  # la previsión empieza en la próxima hora en punto
            temp = hourly["temperature_2m"][i]
            if temp is None:
                continue
            forecast.append(s.WeatherHour(
                time=when, temperature_c=float(temp),
                rain_probability_pct=float(hourly["precipitation_probability"][i] or 0.0),
                rain_mm=float(hourly["precipitation"][i] or 0.0),
            ))
            if len(forecast) == FORECAST_HOURS:
                break
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ValueError(f"Respuesta de Open-Meteo no válida: {e}") from e
    if not forecast:
        raise ValueError("Open-Meteo no devolvió previsión")
    return s.Weather(parcel_id=parcel_id, updated_at=now, current=current, forecast=forecast)


def get_weather(parcel_id: int, latitude: float, longitude: float) -> Optional[s.Weather]:
    """El clima de la parcela, o ``None`` si no se puede saber (sin internet y sin nada guardado)."""
    key = (round(latitude, 2), round(longitude, 2))
    now = _now()
    with _lock:
        cached = _cache.get(key)
        if cached and now - cached[0] < CACHE_TTL:
            return cached[1].model_copy(update={"parcel_id": parcel_id})
        failed = _failed_at.get(key)
        recently_failed = failed is not None and now - failed < RETRY_AFTER

    if not recently_failed:
        try:
            weather = parse(parcel_id, _fetch_json(*key), now)
            with _lock:
                _cache[key] = (now, weather)
                _failed_at.pop(key, None)
            return weather
        except Exception as e:  # sin internet, tiempo agotado, servicio caído, JSON raro…
            log.warning("No se pudo obtener el clima de Open-Meteo: %s", e)
            with _lock:
                _failed_at[key] = now

    if cached and now - cached[0] < STALE_MAX:
        return cached[1].model_copy(update={"parcel_id": parcel_id, "stale": True})
    return None


def clear_cache() -> None:
    with _lock:
        _cache.clear()
        _failed_at.clear()
