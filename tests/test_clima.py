"""Pruebas del clima real (Open-Meteo): conversión, caché, reserva si falla y rutas.

Ninguna llama a internet: ``conftest.py`` hace fallar la llamada y aquí se sustituye por una falsa.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api
from demeter.services import weather

client = TestClient(api)


def respuesta(ahora=None, horas=30, temp=19.3, code=2, prob=40, lluvia=0.0):
    """Una respuesta con la forma de la de Open-Meteo (horas en UTC, sin zona)."""
    ahora = ahora or datetime.now(timezone.utc)
    inicio = ahora.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    tiempos = [(inicio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(horas)]
    return {
        "current": {"time": ahora.strftime("%Y-%m-%dT%H:%M"), "temperature_2m": temp,
                    "relative_humidity_2m": 60, "wind_speed_10m": 10.1, "precipitation": 0.0,
                    "weather_code": code},
        "hourly": {"time": tiempos, "temperature_2m": [temp + i / 10 for i in range(horas)],
                   "precipitation_probability": [prob] * horas, "precipitation": [lluvia] * horas},
    }


@pytest.fixture
def red(monkeypatch):
    """Internet falso: cuenta las llamadas y se le puede mandar fallar."""
    estado = {"llamadas": [], "falla": False, "data": respuesta()}

    def falso(latitude, longitude):
        estado["llamadas"].append((latitude, longitude))
        if estado["falla"]:
            raise OSError("sin internet")
        return estado["data"]

    monkeypatch.setattr(weather, "_fetch_json", falso)
    return estado


@pytest.fixture
def con_bd(api_db):
    return api_db


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- conversión


def test_convierte_la_respuesta_y_la_prevision_empieza_en_la_proxima_hora():
    ahora = datetime.now(timezone.utc)
    w = weather.parse(1, respuesta(ahora), ahora)
    assert (w.current.temperature_c, w.current.humidity_pct, w.current.wind_kmh) == (19.3, 60, 10.1)
    assert w.current.description == "Parcialmente nublado"
    assert len(w.forecast) == 24 and all(h.time > ahora for h in w.forecast)
    assert w.forecast[0].time.minute == 0 and w.forecast[0].time.tzinfo is not None
    assert w.source == "Open-Meteo" and w.stale is False


def test_valores_nulos_de_probabilidad_y_lluvia_cuentan_como_cero():
    ahora = datetime.now(timezone.utc)
    data = respuesta(ahora)
    data["hourly"]["precipitation_probability"] = [None] * 30
    data["hourly"]["precipitation"] = [None] * 30
    w = weather.parse(1, data, ahora)
    assert {h.rain_probability_pct for h in w.forecast} == {0.0}


@pytest.mark.parametrize("estropear", [
    lambda d: d.pop("current"), lambda d: d.pop("hourly"),
    lambda d: d["current"].pop("temperature_2m"), lambda d: d["current"].update(temperature_2m="x"),
    lambda d: d["hourly"].update(time=[]), lambda d: d["hourly"].update(temperature_2m=[]),
])
def test_una_respuesta_rara_es_un_error_claro(estropear):
    ahora = datetime.now(timezone.utc)
    data = respuesta(ahora)
    estropear(data)
    with pytest.raises(ValueError):
        weather.parse(1, data, ahora)


def test_describe_los_codigos_del_tiempo():
    assert weather.describe(0) == "Despejado" and weather.describe(95) == "Tormenta"
    assert weather.describe(12345) == "" and weather.describe(None) == ""


# ---------------------------------------------------------------- caché y reserva


def test_la_segunda_peticion_sale_de_la_cache(red):
    assert weather.get_weather(1, 36.7452, -3.5101) is not None
    assert weather.get_weather(2, 36.7452, -3.5101).parcel_id == 2  # otra parcela, mismo sitio
    assert len(red["llamadas"]) == 1


def test_solo_salen_las_coordenadas_redondeadas(red):
    weather.get_weather(1, 36.745234, -3.510187)
    assert red["llamadas"] == [(36.75, -3.51)]


def test_la_cache_caduca_a_los_10_minutos(red, monkeypatch):
    t0 = datetime.now(timezone.utc)
    monkeypatch.setattr(weather, "_now", lambda: t0)
    weather.get_weather(1, 36.7, -3.5)
    monkeypatch.setattr(weather, "_now", lambda: t0 + timedelta(minutes=11))
    weather.get_weather(1, 36.7, -3.5)
    assert len(red["llamadas"]) == 2


def test_si_falla_se_sirven_los_ultimos_datos_marcados_como_antiguos(red, monkeypatch):
    t0 = datetime.now(timezone.utc)
    monkeypatch.setattr(weather, "_now", lambda: t0)
    assert weather.get_weather(1, 36.7, -3.5).stale is False
    red["falla"] = True
    monkeypatch.setattr(weather, "_now", lambda: t0 + timedelta(minutes=30))
    w = weather.get_weather(1, 36.7, -3.5)
    assert w is not None and w.stale is True
    monkeypatch.setattr(weather, "_now", lambda: t0 + timedelta(hours=7))  # ya demasiado viejo
    assert weather.get_weather(1, 36.7, -3.5) is None


def test_sin_datos_guardados_y_sin_internet_no_se_inventa_nada(red):
    red["falla"] = True
    assert weather.get_weather(1, 36.7, -3.5) is None


def test_tras_un_fallo_no_se_reintenta_hasta_pasado_un_minuto(red, monkeypatch):
    red["falla"] = True
    t0 = datetime.now(timezone.utc)
    monkeypatch.setattr(weather, "_now", lambda: t0)
    weather.get_weather(1, 36.7, -3.5)
    monkeypatch.setattr(weather, "_now", lambda: t0 + timedelta(seconds=30))
    weather.get_weather(1, 36.7, -3.5)
    assert len(red["llamadas"]) == 1
    red["falla"] = False
    monkeypatch.setattr(weather, "_now", lambda: t0 + timedelta(seconds=61))
    assert weather.get_weather(1, 36.7, -3.5) is not None and len(red["llamadas"]) == 2


# ---------------------------------------------------------------- rutas


def test_ruta_de_clima_con_internet(red, con_bd):
    r = client.get("/api/parcels/3/weather", headers=auth("lector"))  # la finca 3 ya funciona
    assert r.status_code == 200
    d = r.json()
    assert d["parcel_id"] == 3 and len(d["forecast"]) == 24 and d["stale"] is False
    assert d["current"]["description"] == "Parcialmente nublado"


def test_ruta_de_clima_sin_internet_503_y_el_dashboard_sigue_vivo(red, con_bd):
    red["falla"] = True
    r = client.get("/api/parcels/1/weather", headers=auth())
    assert r.status_code == 503 and "clima" in r.json()["detail"]
    dash = client.get("/api/dashboard?parcel_id=1", headers=auth())
    assert dash.status_code == 200 and dash.json()["weather"] is None
    assert len(dash.json()["sensors"]) == 5  # lo demás no se ve afectado


def test_el_dashboard_lleva_el_clima_real(red, con_bd):
    d = client.get("/api/dashboard?parcel_id=2", headers=auth()).json()
    assert d["weather"]["current"]["temperature_c"] == 19.3 and d["weather"]["source"] == "Open-Meteo"


def test_clima_permisos_404_y_parcela_de_baja(red, con_bd):
    assert client.get("/api/parcels/1/weather").status_code == 401
    assert client.get("/api/parcels/99/weather", headers=auth()).status_code == 404
    client.patch("/api/parcels/2", json={"is_active": False}, headers=auth())
    assert client.get("/api/parcels/2/weather", headers=auth("lector")).status_code == 404
    assert client.get("/api/parcels/2/weather", headers=auth("admin")).status_code == 200
