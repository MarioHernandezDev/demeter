"""Histórico agregado de un sensor y filtro de fechas de las alertas (mapa de la web: «Histórico»,
«Límites por sensor» y «Últimos 7 días»)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)
KEY = {"X-API-Key": "demo-ingest-key"}


def now():
    return datetime.now(timezone.utc)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def carga(sensor, pares):
    """pares: lista de (hace_cuántos_minutos, valor)."""
    body = {"readings": [{"timestamp": (now() - timedelta(minutes=m)).isoformat(), "value": v} for m, v in pares]}
    assert client.post(f"/api/sensors/{sensor}/data/batch", json=body, headers=KEY).status_code == 200


def historia(sensor="t001", rango=None, role="lector"):
    q = f"?range={rango}" if rango else ""
    return client.get(f"/api/sensors/{sensor}/history{q}", headers=auth(role))


# ---------------------------------------------------------------- forma y rangos


def test_sin_lecturas_no_hay_puntos_ni_resumen():
    r = historia()
    assert r.status_code == 200
    d = r.json()
    assert d["points"] == [] and d["summary"] is None
    assert (d["range"], d["bucket_minutes"]) == ("24h", 10)  # 24 h por defecto
    assert d["type"] == "temperatura" and (d["threshold_low"], d["threshold_high"]) == (8, 35)


@pytest.mark.parametrize("rango,minutos", [("24h", 10), ("7d", 60), ("30d", 360)])
def test_cada_rango_tiene_su_tramo_y_sus_limites(rango, minutos):
    carga("t001", [(5, 20)])
    d = historia(rango=rango).json()
    assert d["bucket_minutes"] == minutos
    desde, hasta = (datetime.fromisoformat(d[k].replace("Z", "+00:00")) for k in ("since", "until"))
    dias = {"24h": 1, "7d": 7, "30d": 30}[rango]
    assert hasta - desde == timedelta(days=dias)
    assert abs((now() - hasta).total_seconds()) < 5


def test_los_tramos_estan_alineados_al_reloj_y_ordenados():
    carga("t001", [(m, 20 + m % 7) for m in range(0, 3000, 7)])  # ~2 días
    for rango, regla in (("24h", lambda t: t.minute % 10 == 0), ("7d", lambda t: t.minute == 0),
                         ("30d", lambda t: t.minute == 0 and t.hour % 6 == 0)):
        puntos = historia(rango=rango).json()["points"]
        tiempos = [datetime.fromisoformat(p["time"].replace("Z", "+00:00")) for p in puntos]
        assert tiempos == sorted(tiempos) and len(set(tiempos)) == len(tiempos)
        assert all(regla(t) and t.second == 0 for t in tiempos), rango


# ---------------------------------------------------------------- los números


def test_resumen_y_tramos_cuadran_con_las_lecturas():
    valores = [10, 20, 30, 40, 50]
    carga("t001", [(m, v) for m, v in zip((1, 2, 3, 4, 5), valores)])
    d = historia().json()
    assert d["summary"] == {"min": 10, "avg": 30, "max": 50, "count": 5}
    assert sum(p["count"] for p in d["points"]) == 5
    assert min(p["min"] for p in d["points"]) == 10 and max(p["max"] for p in d["points"]) == 50
    for p in d["points"]:
        assert p["min"] <= p["avg"] <= p["max"] and p["count"] >= 1


def test_la_media_del_rango_pesa_por_lecturas_no_por_tramos():
    # un tramo con 1 lectura de 100 y otro con 9 lecturas de 0 (separados una hora): media 10, no 50
    carga("t001", [(70, 100)] + [(m, 0) for m in range(1, 10)])
    d = historia(rango="24h").json()
    assert d["summary"]["avg"] == pytest.approx(10) and d["summary"]["count"] == 10


def test_solo_cuenta_lo_que_cae_dentro_del_rango():
    carga("t001", [(5, 20), (60 * 24 * 3, 99), (60 * 24 * 40, 99)])  # hace 3 y 40 días
    assert historia(rango="24h").json()["summary"]["count"] == 1
    assert historia(rango="7d").json()["summary"]["count"] == 2
    assert historia(rango="30d").json()["summary"]["count"] == 2
    assert historia(rango="7d").json()["summary"]["max"] == 99


def test_un_hueco_en_los_datos_es_un_hueco_en_la_lista():
    carga("t001", [(5, 20), (60 * 10, 21)])  # hace 5 min y hace 10 h
    puntos = historia(rango="24h").json()["points"]
    assert len(puntos) == 2  # no se rellenan los tramos intermedios


def test_no_mezcla_sensores():
    carga("t001", [(5, 20)])
    carga("h001", [(5, 50), (6, 60)])
    assert historia("t001").json()["summary"]["count"] == 1
    assert historia("h001").json()["summary"] == {"min": 50, "avg": 55, "max": 60, "count": 2}


def test_muchas_lecturas_se_resumen_en_pocos_puntos():
    carga("t001", [(m, 20.0) for m in range(1, 1001)])
    carga("t001", [(m, 20.0) for m in range(1001, 2001)])
    d = historia(rango="24h").json()
    # 2000 lecturas, de las que solo caben ~1440 en 24 h (la más antigua justo en el borde)
    assert 1438 <= d["summary"]["count"] <= 1440 and len(d["points"]) <= 145


# ---------------------------------------------------------------- permisos y errores


def test_permisos_404_y_rango_invalido():
    assert client.get("/api/sensors/t001/history").status_code == 401
    assert historia("zzz").status_code == 404
    assert historia(rango="1h").status_code == 422
    assert historia(rango="año").status_code == 422


def test_un_lector_no_ve_el_historico_de_un_sensor_de_baja():
    carga("t001", [(5, 20)])
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth())
    assert historia(role="lector").status_code == 404
    assert historia(role="tecnico").json()["summary"]["count"] == 1
    client.patch("/api/sensors/t001", json={"is_active": True}, headers=auth())
    client.patch("/api/parcels/1", json={"is_active": False}, headers=auth())
    assert historia(role="lector").status_code == 404
    assert historia(role="admin").status_code == 200


# ---------------------------------------------------------------- alertas: últimos 7 días


def abre(sensor, minutos):
    body = {"timestamp": (now() - timedelta(minutes=minutos)).isoformat(), "value": 99}
    assert client.post(f"/api/sensors/{sensor}/data", json=body, headers=KEY).status_code == 200


def test_alertas_desde_una_fecha():
    # t001 (máx 35) abre una alerta hace 20 h; h001 (máx 60) otra hace 3 min
    abre("t001", 60 * 20)
    abre("h001", 3)
    todas = client.get("/api/alerts", headers=auth()).json()
    assert len(todas) == 2
    desde = (now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = client.get(f"/api/alerts?since={desde}", headers=auth())
    assert [a["sensor_id"] for a in r.json()] == ["h001"] and r.headers["X-Total-Count"] == "1"
    hace_un_dia = (now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert len(client.get(f"/api/alerts?since={hace_un_dia}", headers=auth()).json()) == 2
    futuro = (now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert client.get(f"/api/alerts?since={futuro}", headers=auth()).json() == []


def test_alertas_desde_sin_zona_horaria_se_toma_como_utc_y_fecha_mala_422():
    abre("h001", 3)
    ayer = (now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    assert len(client.get(f"/api/alerts?since={ayer}", headers=auth()).json()) == 1
    assert client.get("/api/alerts?since=ayer", headers=auth()).status_code == 422
