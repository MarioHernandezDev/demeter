"""Pruebas de la ingesta y el histórico (A5, issue #23), contra una BD en memoria con el seed.

El seed trae 3 fincas y 14 sensores; t001 tiene umbral mínimo 8 y máximo 35.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

from demeter.api.app import api
from demeter.db import conexion
from demeter.models import Alert, SensorData

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)
KEY = {"X-API-Key": "demo-ingest-key"}


def now():
    return datetime.now(timezone.utc)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def post(value, when=None, sensor="t001", headers=KEY):
    body = {"value": value}
    if when is not None:
        body["timestamp"] = when.isoformat()
    return client.post(f"/api/sensors/{sensor}/data", json=body, headers=headers)


def alertas():
    with conexion.open_session() as s:
        return list(s.exec(select(Alert)).all())


def n_lecturas():
    with conexion.open_session() as s:
        return len(s.exec(select(SensorData)).all())


# ---------------------------------------------------------------- ingesta en vivo


def test_guarda_la_lectura_y_se_ve_en_el_historico():
    t = now()
    r = post(21.5, t)
    assert r.status_code == 200 and r.json()["stored"] is True and r.json()["duplicate"] is False
    lecturas = client.get("/api/sensors/t001/data", headers=auth("lector")).json()
    assert [x["value"] for x in lecturas] == [21.5]


def test_sin_timestamp_usa_la_hora_de_llegada():
    antes = now()
    r = post(21.5)
    assert r.status_code == 200
    t = datetime.fromisoformat(r.json()["timestamp"].replace("Z", "+00:00"))
    assert antes - timedelta(seconds=1) <= t <= now() + timedelta(seconds=1)


def test_una_lectura_repetida_se_ignora():
    t = now()
    assert post(21.5, t).json()["stored"] is True
    r = post(21.5, t)
    assert r.status_code == 200 and r.json() == {**r.json(), "stored": False, "duplicate": True}
    assert n_lecturas() == 1


def test_clave_mala_o_ausente_401_y_no_se_guarda_nada():
    assert post(21.5, headers={}).status_code == 401
    assert post(21.5, headers={"X-API-Key": "otra"}).status_code == 401
    assert n_lecturas() == 0


def test_sensor_inexistente_404():
    assert post(21.5, sensor="zzz").status_code == 404


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "abc"])
def test_valores_no_validos_422(value):
    r = client.post("/api/sensors/t001/data", content=f'{{"value": {value}}}'.replace('abc', '"abc"'),
                    headers={**KEY, "Content-Type": "application/json"})
    assert r.status_code == 422
    assert n_lecturas() == 0


def test_horas_demasiado_antiguas_o_futuras_422():
    assert post(21.5, datetime(1970, 1, 1, tzinfo=timezone.utc)).status_code == 422
    assert post(21.5, now() - timedelta(hours=25)).status_code == 422
    assert post(21.5, now() + timedelta(minutes=10)).status_code == 422
    assert post(21.5, now() - timedelta(hours=23)).status_code == 200
    assert post(21.5, now() + timedelta(minutes=1)).status_code == 200


def test_hora_sin_zona_se_toma_como_utc():
    t = (now() - timedelta(minutes=1)).replace(tzinfo=None)
    r = post(21.5, t)
    assert r.status_code == 200
    assert r.json()["timestamp"].startswith(t.isoformat()[:19])


# ---------------------------------------------------------------- alertas en la misma transacción


def test_una_lectura_fuera_de_umbral_abre_una_alerta_una_sola_vez():
    t = now() - timedelta(minutes=5)
    post(50, t)  # t001: máximo 35
    post(51, t + timedelta(minutes=1))
    abiertas = [a for a in alertas() if a.resolved_at is None]
    assert len(abiertas) == 1 and abiertas[0].type == "HIGH" and abiertas[0].sensor_id == "t001"


def test_volver_a_la_normalidad_cierra_la_alerta():
    t = now() - timedelta(minutes=5)
    post(50, t)
    post(20, t + timedelta(minutes=1))
    assert all(a.resolved_at is not None for a in alertas()) and len(alertas()) == 1


def test_un_duplicado_no_toca_las_alertas():
    t = now() - timedelta(minutes=5)
    post(50, t)
    post(20, t)  # misma hora: duplicado, se ignora aunque el valor sea normal
    assert [a.resolved_at for a in alertas()] == [None]


def test_una_lectura_atrasada_se_guarda_pero_no_genera_alertas():
    t = now() - timedelta(minutes=5)
    post(20, t)
    assert post(50, t - timedelta(minutes=2)).json()["stored"] is True
    assert alertas() == []


def test_un_sensor_desactivado_guarda_pero_no_alerta():
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth())
    assert post(50, now()).status_code == 200
    assert n_lecturas() == 1 and alertas() == []


# ---------------------------------------------------------------- histórico (batch)


def lote(n, desde=None, valor=20.0):
    desde = desde or now() - timedelta(days=2)
    return {"readings": [{"timestamp": (desde + timedelta(minutes=i)).isoformat(), "value": valor}
                         for i in range(n)]}


def test_carga_de_historico_cuenta_guardadas_y_repetidas():
    body = lote(10)
    r = client.post("/api/sensors/t001/data/batch", json=body, headers=KEY)
    assert r.status_code == 200 and (r.json()["received"], r.json()["stored"]) == (10, 10)
    r = client.post("/api/sensors/t001/data/batch", json=body, headers=KEY)
    assert (r.json()["stored"], r.json()["duplicates"]) == (0, 10)
    assert n_lecturas() == 10


def test_el_historico_no_genera_alertas_aunque_este_fuera_de_umbral():
    r = client.post("/api/sensors/t001/data/batch", json=lote(5, valor=99), headers=KEY)
    assert r.json()["stored"] == 5 and alertas() == []


def test_historico_pide_clave_y_valida_sensor_y_horas():
    assert client.post("/api/sensors/t001/data/batch", json=lote(1)).status_code == 401
    assert client.post("/api/sensors/zzz/data/batch", json=lote(1), headers=KEY).status_code == 404
    viejo = {"readings": [{"timestamp": "1970-01-01T00:00:00Z", "value": 1}]}
    assert client.post("/api/sensors/t001/data/batch", json=viejo, headers=KEY).status_code == 422
    futuro = {"readings": [{"timestamp": (now() + timedelta(days=1)).isoformat(), "value": 1}]}
    assert client.post("/api/sensors/t001/data/batch", json=futuro, headers=KEY).status_code == 422
    assert client.post("/api/sensors/t001/data/batch", json={"readings": []}, headers=KEY).status_code == 422
    assert client.post("/api/sensors/t001/data/batch", json=lote(1001), headers=KEY).status_code == 422
    assert n_lecturas() == 0


def test_un_lote_con_un_valor_malo_no_guarda_nada():
    body = lote(3)
    body["readings"][2]["value"] = "x"
    assert client.post("/api/sensors/t001/data/batch", json=body, headers=KEY).status_code == 422
    assert n_lecturas() == 0


# ---------------------------------------------------------------- consultar el histórico


def test_consulta_con_limit_since_y_orden():
    t = now() - timedelta(minutes=10)
    for i in range(6):
        post(10 + i, t + timedelta(minutes=i))
    h = auth("lector")
    todas = client.get("/api/sensors/t001/data", headers=h).json()
    assert [x["value"] for x in todas] == [10, 11, 12, 13, 14, 15]  # antigua → reciente
    assert [x["value"] for x in client.get("/api/sensors/t001/data?limit=2", headers=h).json()] == [14, 15]
    desde = (t + timedelta(minutes=3)).isoformat().replace("+00:00", "Z")
    assert [x["value"] for x in client.get(f"/api/sensors/t001/data?since={desde}", headers=h).json()] == [14, 15]
    assert client.get("/api/sensors/t001/data?since=ayer", headers=h).status_code == 422


def test_consulta_exige_token_y_404_si_no_existe():
    assert client.get("/api/sensors/t001/data").status_code == 401
    assert client.get("/api/sensors/zzz/data", headers=auth()).status_code == 404


def test_un_lector_no_ve_las_lecturas_de_un_sensor_dado_de_baja():
    post(21.5, now())
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth())
    assert client.get("/api/sensors/t001/data", headers=auth("lector")).status_code == 404
    assert len(client.get("/api/sensors/t001/data", headers=auth("tecnico")).json()) == 1
