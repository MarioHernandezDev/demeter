"""Pruebas de las alertas y el dashboard desde la base de datos (A6, issue #24).

Seed: 3 fincas (1, 2, 3) y 14 sensores. t001 (finca 1) tiene umbral mínimo 8 y máximo 35.
Las alertas se crean como en la vida real: ingiriendo lecturas y dejando actuar al motor.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api
from demeter.db import conexion
from demeter.services.alerts import comprobar_offline
from demeter.state.types import DashboardSummary as UiDashboard

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)
KEY = {"X-API-Key": "demo-ingest-key"}


def now():
    return datetime.now(timezone.utc)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def post(sensor, value, when=None):
    body = {"value": value, **({"timestamp": when.isoformat()} if when else {})}
    assert client.post(f"/api/sensors/{sensor}/data", json=body, headers=KEY).status_code == 200


def fuera(x):
    """Un valor fuera de umbral para el sensor ``x`` (el máximo o el mínimo, según tenga)."""
    return x["threshold_high"] + 10 if x["threshold_high"] is not None else x["threshold_low"] - 10


def abre_alta(sensor="t001", minutos=5):
    post(sensor, 50, now() - timedelta(minutes=minutos))


def lista(query="", role="admin"):
    return client.get(f"/api/alerts{query}", headers=auth(role))


# ---------------------------------------------------------------- GET /alerts


def test_sin_alertas_lista_vacia_y_total_cero():
    r = lista()
    assert r.status_code == 200 and r.json() == [] and r.headers["X-Total-Count"] == "0"


def test_lista_la_alerta_con_sus_campos():
    abre_alta()
    [a] = lista("?parcel_id=1", "lector").json()
    assert a["type"] == "HIGH" and a["sensor_id"] == "t001"
    assert a["value"] == 50 and a["threshold"] == 35 and a["resolved_at"] is None
    assert a["acknowledged"] is False


def test_paginacion_y_total():
    # los 5 sensores de la finca 1 abren una alerta cada uno
    for x in client.get("/api/parcels/1/sensors", headers=auth()).json():
        post(x["id"], fuera(x), now() - timedelta(minutes=5))
    r = lista("?limit=2")
    assert len(r.json()) == 2 and r.headers["X-Total-Count"] == "5"
    r2 = lista("?limit=2&offset=4")
    assert len(r2.json()) == 1 and r2.headers["X-Total-Count"] == "5"
    assert lista("?limit=0").status_code == 422 and lista("?offset=-1").status_code == 422


def test_filtros_tipo_sensor_activa_y_parcela():
    t = now() - timedelta(minutes=5)
    post("t001", 50, t)  # HIGH
    post("t001", 20, t + timedelta(minutes=1))  # la cierra
    assert lista("?active=true").json() == [] and len(lista("?active=false").json()) == 1
    assert len(lista("?type=HIGH").json()) == 1 and lista("?type=LOW").json() == []
    assert len(lista("?sensor_id=t001").json()) == 1 and lista("?sensor_id=t002").json() == []
    assert len(lista("?parcel_id=1").json()) == 1 and lista("?parcel_id=2").json() == []
    assert lista("?type=OTRA").status_code == 422


def test_alertas_exigen_token_y_la_parcela_debe_existir():
    assert client.get("/api/alerts").status_code == 401
    assert lista("?parcel_id=99").status_code == 404


def test_un_lector_no_pide_alertas_de_una_parcela_de_baja():
    client.patch("/api/parcels/1", json={"is_active": False}, headers=auth())
    assert lista("?parcel_id=1", "lector").status_code == 404
    assert lista("?parcel_id=1", "admin").status_code == 200


# ---------------------------------------------------------------- marcar como leída


def test_marcar_una_alerta_como_leida_y_volver_a_dejarla():
    abre_alta()
    aid = lista().json()[0]["id"]
    r = client.patch(f"/api/alerts/{aid}", json={"acknowledged": True}, headers=auth("tecnico"))
    assert r.status_code == 200 and r.json()["acknowledged"] is True
    assert lista("?unread_only=true").json() == []
    client.patch(f"/api/alerts/{aid}", json={"acknowledged": False}, headers=auth("tecnico"))
    assert len(lista("?unread_only=true").json()) == 1


def test_marcar_alerta_permisos_y_404():
    abre_alta()
    aid = lista().json()[0]["id"]
    assert client.patch(f"/api/alerts/{aid}", json={"acknowledged": True}, headers=auth("lector")).status_code == 403
    assert client.patch("/api/alerts/999", json={"acknowledged": True}, headers=auth()).status_code == 404


def test_ack_all_marca_las_de_la_parcela_y_repetir_da_cero():
    abre_alta("t001")  # finca 1
    post("h001", 70, now() - timedelta(minutes=5))  # finca 1 (máximo 60)
    post("h002", 99, now() - timedelta(minutes=5))  # finca 2: no debe tocarse
    r = client.post("/api/alerts/ack-all?parcel_id=1", headers=auth("tecnico"))
    assert r.status_code == 200 and r.json() == {"updated": 2}
    assert client.post("/api/alerts/ack-all?parcel_id=1", headers=auth("tecnico")).json() == {"updated": 0}
    assert len(lista("?parcel_id=2&unread_only=true").json()) == 1


def test_ack_all_permisos_y_parcela_inexistente():
    assert client.post("/api/alerts/ack-all?parcel_id=1", headers=auth("lector")).status_code == 403
    assert client.post("/api/alerts/ack-all?parcel_id=99", headers=auth()).status_code == 404
    assert client.post("/api/alerts/ack-all", headers=auth()).status_code == 422
    assert client.post("/api/alerts/ack-all?parcel_id=1").status_code == 401


# ---------------------------------------------------------------- dashboard


def dash(pid=1, role="lector"):
    return client.get(f"/api/dashboard?parcel_id={pid}", headers=auth(role))


def test_dashboard_sin_lecturas_todo_sin_datos_y_lo_entiende_la_interfaz():
    r = dash()
    assert r.status_code == 200
    d = r.json()
    assert len(d["sensors"]) == 5 and {x["status"] for x in d["sensors"]} == {"sin_datos"}
    assert d["alerts"] == [] and d["unread_alerts"] == 0
    assert all(x["last"] is None and x["recent"] == [] for x in d["sensors"])
    assert UiDashboard.from_api(d).parcel.name  # el tipo que usa la interfaz


def test_dashboard_ultimo_valor_estado_y_mini_historico():
    t = now() - timedelta(minutes=30)
    for i in range(25):  # 25 lecturas normales de t001 (rango 8–35)
        post("t001", 20 + i % 3, t + timedelta(minutes=i))
    snap = next(x for x in dash().json()["sensors"] if x["sensor"]["id"] == "t001")
    assert snap["status"] == "ok" and snap["last"]["value"] == 20 + 24 % 3
    assert len(snap["recent"]) == 20 and snap["recent"][-1] == snap["last"]["value"]


def test_dashboard_estado_alto_y_offline():
    post("t001", 50, now() - timedelta(minutes=2))
    post("a001", 50, now() - timedelta(minutes=15))
    snaps = {x["sensor"]["id"]: x["status"] for x in dash().json()["sensors"]}
    assert snaps["t001"] == "HIGH" and snaps["a001"] == "offline"


def test_dashboard_alertas_activas_primero_maximo_5_y_sin_leer_son_todas():
    # 5 sensores de la finca 1 abren una alerta; t001 la cierra después (queda resuelta)
    sensores = client.get("/api/parcels/1/sensors", headers=auth()).json()
    t = now() - timedelta(minutes=10)
    for x in sensores:
        post(x["id"], fuera(x), t)
    post("t001", 20, t + timedelta(minutes=1))  # cierra la de t001
    with conexion.open_session() as session:
        comprobar_offline(session, now() + timedelta(hours=1))  # abre una OFFLINE por sensor
        session.commit()
    d = dash().json()
    assert len(d["alerts"]) == 5
    activas = [a["resolved_at"] is None for a in d["alerts"]]
    assert activas == sorted(activas, reverse=True)  # activas antes que resueltas
    total_sin_leer = int(lista("?parcel_id=1&unread_only=true").headers["X-Total-Count"])
    assert d["unread_alerts"] == total_sin_leer and total_sin_leer > 5


def test_dashboard_parcela_inexistente_baja_y_token():
    assert dash(99).status_code == 404
    client.patch("/api/parcels/2", json={"is_active": False}, headers=auth())
    assert dash(2, "lector").status_code == 404 and dash(2, "admin").status_code == 200
    assert client.get("/api/dashboard").status_code == 401


def test_el_lector_no_ve_en_el_dashboard_los_sensores_desactivados():
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth())
    ids = lambda role: {x["sensor"]["id"] for x in dash(1, role).json()["sensors"]}
    assert "t001" not in ids("lector") and "t001" in ids("tecnico")
