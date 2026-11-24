"""Pruebas del WebSocket del dashboard (A7, issue #25)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from demeter.api import routes
from demeter.api.app import api

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)
KEY = {"X-API-Key": "demo-ingest-key"}


@pytest.fixture(autouse=True)
def rapido(monkeypatch):
    monkeypatch.setattr(routes, "WS_POLL_SECONDS", 0.05)


def token(role="lector"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return r.json()["access_token"]


def url(parcel_id=1, tok=None):
    return f"/api/ws/dashboard?parcel_id={parcel_id}&token={tok if tok is not None else token()}"


def post(sensor, value):
    when = datetime.now(timezone.utc) - timedelta(seconds=1)
    body = {"value": value, "timestamp": when.isoformat()}
    assert client.post(f"/api/sensors/{sensor}/data", json=body, headers=KEY).status_code == 200


def test_al_conectar_envia_el_dashboard_igual_que_el_get():
    headers = {"Authorization": f"Bearer {token()}"}
    with client.websocket_connect(url()) as ws:
        msg = ws.receive_json()
    assert msg["type"] == "dashboard"
    rest = client.get("/api/dashboard?parcel_id=1", headers=headers).json()
    assert msg["data"]["parcel"] == rest["parcel"] and len(msg["data"]["sensors"]) == 5
    assert {x["status"] for x in msg["data"]["sensors"]} == {"sin_datos"}


def test_envia_de_nuevo_cuando_cambia_algo_y_no_si_nada_cambia():
    with client.websocket_connect(url()) as ws:
        ws.receive_json()
        post("t001", 50)  # fuera de umbral: cambia la tarjeta y se abre una alerta
        msg = ws.receive_json()
        snap = next(x for x in msg["data"]["sensors"] if x["sensor"]["id"] == "t001")
        assert snap["status"] == "HIGH" and msg["data"]["unread_alerts"] == 1
        # sin cambios no manda nada: lo siguiente que llega es la respuesta al ping
        ws.send_text("ping")
        assert ws.receive_json() == {"type": "pong"}


@pytest.mark.parametrize("tok", ["", "basura"])
def test_sin_token_valido_se_rechaza(tok):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(url(tok=tok)):
            pass
    assert e.value.code == 1008


def test_parcela_inexistente_o_de_baja_para_un_lector():
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(url(99)):
            pass
    assert e.value.code == 1008
    client.patch("/api/parcels/2", json={"is_active": False},
                 headers={"Authorization": f"Bearer {token('admin')}"})
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(url(2)):
            pass
    with client.websocket_connect(url(2, token("admin"))) as ws:  # el admin sí
        assert ws.receive_json()["type"] == "dashboard"


def test_se_cierra_si_la_parcela_se_da_de_baja_mientras_esta_abierto():
    admin = {"Authorization": f"Bearer {token('admin')}"}
    with client.websocket_connect(url(2)) as ws:
        ws.receive_json()
        client.patch("/api/parcels/2", json={"is_active": False}, headers=admin)
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
        assert e.value.code == 1008
