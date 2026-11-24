"""Coherencia de la predicción y del riego (E8, issue #9).

Además de los casos concretos de ``test_forecast.py`` y ``test_irrigation.py``, aquí se
comprueba que las reglas del contrato (docs/insights-contrato.md) se cumplen **siempre**:

- por la API, con todos los sensores y parcelas de ejemplo;
- con cientos de escenarios aleatorios (semilla fija, así que el resultado es reproducible);
- y que las fórmulas responden en el sentido que esperaría un agricultor (más seco o más
  calor → más agua; más lluvia → menos agua; más agua en el depósito → nunca menos riego).
"""

import math
import random
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from demeter.api import sample_data as d
from demeter.api import schemas as s
from demeter.api.app import api
from demeter.api.geo import offset, rectangle
from demeter.services.forecast import predict_sensor
from demeter.services.irrigation import recommend

client = TestClient(api)
MADRID = ZoneInfo("Europe/Madrid")
NOW = datetime(2026, 11, 24, 10, 20, tzinfo=timezone.utc)
LAT, LON = 36.7174, -3.4301


def _token() -> dict:
    r = client.post("/api/auth/login", json={"username": "lector", "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


HEADERS = _token()


# ------------------------------------------------------------------ comprobaciones del contrato


def assert_prediction_ok(p: s.SensorPrediction, sensor: s.Sensor, current: float):
    low, high = sensor.threshold_low, sensor.threshold_high
    assert len(p.points) == 24
    first = p.points[0].time
    assert first.minute == 0 and first > p.generated_at and first - p.generated_at <= timedelta(hours=1)
    assert all(b.time - a.time == timedelta(hours=1) for a, b in zip(p.points, p.points[1:]))
    for x in p.points:
        assert x.lower <= x.value <= x.upper
        assert all(math.isfinite(v) for v in (x.value, x.lower, x.upper))
        if sensor.unit == "%":
            assert 0 <= x.lower and x.upper <= 100
    # Tendencia: coherente con el primer y el último punto.
    delta = p.points[-1].value - p.points[0].value
    if p.trend == "rising":
        assert delta > 0
    elif p.trend == "falling":
        assert delta < 0
    # Cruce: el primer punto fuera de umbral, y solo si hoy está dentro.
    def fuera(v):
        return (low is not None and v < low) or (high is not None and v > high)

    if p.crossing is None:
        assert fuera(current) or not any(fuera(x.value) for x in p.points)
    else:
        assert not fuera(current)
        idx = next(i for i, x in enumerate(p.points) if fuera(x.value))
        assert p.crossing.at == p.points[idx].time and p.crossing.value == p.points[idx].value
        assert p.crossing.type == ("LOW" if low is not None and p.crossing.value < low else "HIGH")


def assert_advice_ok(a: s.IrrigationAdvice, zones: list[s.Zone], now: datetime):
    assert a.summary
    assert a.total_liters == pytest.approx(sum(z.liters for z in a.zones), abs=0.2)
    assert a.enough_water == (a.available_l >= a.total_liters)
    assert a.total_liters <= a.available_l + 0.2  # nunca pide más agua de la que hay
    if a.action in ("wait", "skip"):
        assert a.zones == [] and a.total_liters == 0
        return
    assert a.zones, "irrigate siempre trae el reparto"
    crop_ids = {z.id for z in zones if z.type == "crop"}
    assert {z.zone_id for z in a.zones} <= crop_ids
    for z in a.zones:
        assert z.liters > 0 and z.duration_min >= 1
        assert z.start_at > now
    first = a.zones[0].start_at.astimezone(MADRID)
    assert 5 <= first.hour <= 8
    for prev, nxt in zip(a.zones, a.zones[1:]):  # una zona detrás de otra
        assert nxt.start_at == prev.start_at + timedelta(minutes=prev.duration_min)


# ------------------------------------------------------------------ por la API con los datos de ejemplo


@pytest.mark.parametrize("sensor", d.SENSORS, ids=lambda x: x.id)
def test_api_prediccion_de_cada_sensor(sensor):
    r = client.get(f"/api/sensors/{sensor.id}/prediction", headers=HEADERS)
    assert r.status_code == 200
    p = s.SensorPrediction.model_validate(r.json())
    assert p.sensor_id == sensor.id and p.type == sensor.type and p.unit == sensor.unit
    assert_prediction_ok(p, sensor, d.last_reading(sensor).value)


@pytest.mark.parametrize("parcel_id", sorted(d.PARCELS))
def test_api_riego_de_cada_parcela(parcel_id):
    r = client.get(f"/api/parcels/{parcel_id}/irrigation", headers=HEADERS)
    assert r.status_code == 200
    a = s.IrrigationAdvice.model_validate(r.json())
    assert a.parcel_id == parcel_id
    assert_advice_ok(a, [z for z in d.ZONES if z.parcel_id == parcel_id], a.generated_at)


def test_api_riego_y_deposito_cuentan_la_misma_agua():
    a = client.get("/api/parcels/1/irrigation", headers=HEADERS).json()
    w = client.get("/api/parcels/1/water", headers=HEADERS).json()
    assert a["available_l"] == pytest.approx(w["available_l"])
    assert a["factors"]["tank_level_pct"] == pytest.approx(w["level_pct"])


# ------------------------------------------------------------------ escenarios aleatorios


def _random_series(rng: random.Random, tipo: str):
    horas = rng.choice([3, 6, 12, 24, 36, 48])
    cada = rng.choice([1, 5, 15, 30])
    base, ruido = rng.uniform(5, 80), rng.uniform(0, 3)
    pendiente = rng.uniform(-2, 2)
    amplitud = rng.uniform(0, 10) if tipo == "temperatura" else 0
    out = []
    n = int(horas * 60 / cada)
    for i in range(n, -1, -1):
        t = NOW - timedelta(minutes=i * cada)
        h = (t - NOW) / timedelta(hours=1)
        v = base + pendiente * h + amplitud * math.sin(2 * math.pi * (t.hour - 9) / 24) + rng.gauss(0, ruido)
        if rng.random() < 0.05:
            continue  # huecos
        out.append((t, max(0.0, min(100.0, v)) if tipo == "humedad_suelo" else v))
    return out


@pytest.mark.parametrize("seed", range(150))
def test_prediccion_cumple_el_contrato_en_cualquier_escenario(seed):
    rng = random.Random(seed)
    tipo = rng.choice(["temperatura", "humedad_suelo"])
    unit = "%" if tipo == "humedad_suelo" else "ºC"
    low = rng.choice([None, rng.uniform(5, 30)])
    high = rng.choice([None, (low or 0) + rng.uniform(10, 50)])
    sensor = s.Sensor(id="x", parcel_id=1, type=tipo, unit=unit, threshold_low=low, threshold_high=high)
    series = _random_series(rng, tipo)
    p = predict_sensor(sensor, series, NOW)
    assert p is not None
    assert_prediction_ok(p, sensor, series[-1][1])
    assert predict_sensor(sensor, series, NOW) == p  # determinista


def _zone(id, crop, w, h, dy):
    b = rectangle(LAT, LON, w, h, 0, dy)
    return s.Zone(id=id, parcel_id=1, name=f"Z{id}", type="crop", crop=crop, boundary=b, area_m2=w * h)


def _forecast(t_min, t_max, prob, mm):
    return [s.WeatherHour(time=NOW + timedelta(hours=k),
                          temperature_c=t_min + (t_max - t_min) * (0.5 + 0.5 * math.sin((k - 4) / 24 * 2 * math.pi)),
                          rain_probability_pct=prob, rain_mm=mm / 24) for k in range(1, 25)]


def _scenario(rng: random.Random):
    zones = [_zone(i, rng.choice(["aguacate", "mango", "tomate", "chirimoya", None]),
                   rng.uniform(10, 150), rng.uniform(10, 60), 70 * i) for i in range(1, rng.randint(1, 4) + 1)]
    sensors = []
    for i, z in enumerate(zones):
        if rng.random() < 0.7:
            lon, lat = offset(LAT, LON, 0, 70 * (i + 1))
            sensors.append((s.Sensor(id=f"h{i}", parcel_id=1, type="humedad_suelo", unit="%",
                                     threshold_low=25, threshold_high=60, latitude=lat, longitude=lon),
                            rng.uniform(5, 70)))
    t_min = rng.uniform(0, 25)
    forecast = _forecast(t_min, t_min + rng.uniform(2, 15), rng.uniform(0, 100), rng.choice([0, 0, 1, 3, 10]))
    tanks = [s.Tank(id=j, parcel_id=1, name="D", capacity_l=20000, available_l=rng.uniform(0, 20000))
             for j in range(rng.randint(0, 2))]
    return zones, sensors, forecast, tanks


@pytest.mark.parametrize("seed", range(150))
def test_riego_cumple_el_contrato_en_cualquier_escenario(seed):
    rng = random.Random(seed)
    zones, sensors, forecast, tanks = _scenario(rng)
    a = recommend(1, zones, sensors, forecast, tanks, NOW, latitude=LAT)
    assert_advice_ok(a, zones, NOW)


# ------------------------------------------------------------------ las fórmulas van en el sentido correcto


def _liters(soil=18.0, t=(12, 22), prob=10, mm=0.0, water=1e6):
    zones = [_zone(1, "aguacate", 100, 50, 0)]
    lon, lat = offset(LAT, LON, 0, 0)
    sensor = s.Sensor(id="h", parcel_id=1, type="humedad_suelo", unit="%", threshold_low=25,
                      threshold_high=60, latitude=lat, longitude=lon)
    tank = s.Tank(id=1, parcel_id=1, name="D", capacity_l=max(water, 1), available_l=water)
    return recommend(1, zones, [(sensor, soil)], _forecast(*t, prob, mm), [tank], NOW, latitude=LAT).total_liters


def test_mas_seco_nunca_pide_menos_agua():
    seq = [_liters(soil=v) for v in (29, 26, 22, 18, 12, 5)]
    assert seq == sorted(seq)


def test_mas_calor_nunca_pide_menos_agua():
    seq = [_liters(t=(tmin, tmin + 10)) for tmin in (5, 10, 15, 20, 25)]
    assert seq == sorted(seq) and seq[-1] > seq[0]


def test_mas_lluvia_nunca_pide_mas_agua():
    seq = [_liters(prob=50, mm=mm) for mm in (0, 0.5, 1, 2, 3)]
    assert seq == sorted(seq, reverse=True) and seq[-1] < seq[0]


def test_mas_agua_en_el_deposito_nunca_riega_menos():
    seq = [_liters(water=w) for w in (0, 1000, 5000, 20000, 1e6)]
    assert seq == sorted(seq)
