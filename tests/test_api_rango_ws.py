"""Issues #23 y #25: rango físico en la ingesta, filtros ``from`` y ``to`` y WebSocket por parcela."""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from demeter.api import routes
from demeter.api.app import api
from demeter.api.ranges import PHYSICAL_RANGE, out_of_range
from demeter.services import eventos

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)
KEY = {"X-API-Key": "demo-ingest-key"}


def now():
    return datetime.now(timezone.utc)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def token(role="lector"):
    return auth(role)["Authorization"].split()[1]


def post(sensor, value, minutes_ago=0):
    body = {"value": value, "timestamp": (now() - timedelta(minutes=minutes_ago, seconds=1)).isoformat()}
    return client.post(f"/api/sensors/{sensor}/data", json=body, headers=KEY)


# ---------------------------------------------------------------- rango físico


def test_la_tabla_cubre_todos_los_tipos_de_sensor():
    from typing import get_args

    from demeter.api.schemas import SensorType

    assert set(PHYSICAL_RANGE) == set(get_args(SensorType))


@pytest.mark.parametrize("sensor,tipo", [("t001", "temperatura"), ("h001", "humedad_suelo"),
                                          ("a001", "humedad_ambiente"), ("d001", "nivel_deposito"),
                                          ("l001", "luminosidad")])
def test_los_extremos_del_rango_valen_y_un_poco_mas_alla_no(sensor, tipo):
    low, high = PHYSICAL_RANGE[tipo]
    assert post(sensor, low, minutes_ago=2).status_code == 200
    assert post(sensor, high, minutes_ago=3).status_code == 200
    for malo in (low - 0.5, high + 0.5, high * 50 + 1000):
        r = post(sensor, malo, minutes_ago=4)
        assert r.status_code == 422 and "rango físico" in r.json()["detail"], malo


def test_una_lectura_imposible_no_se_guarda_ni_abre_alerta_ni_se_avisa():
    assert post("t001", 5000).status_code == 422
    assert client.get("/api/sensors/t001/data", headers=auth()).json() == []
    assert client.get("/api/alerts", headers=auth()).json() == []


def test_el_mensaje_dice_el_valor_el_tipo_y_el_rango():
    detail = post("h001", 150).json()["detail"]
    assert "150" in detail and "humedad_suelo" in detail and "0 a 100" in detail


def test_sensor_inexistente_sigue_siendo_404_y_clave_mala_401_antes_que_el_rango():
    assert post("zzz", 5000).status_code == 404
    r = client.post("/api/sensors/t001/data", json={"value": 5000}, headers={"X-API-Key": "mala"})
    assert r.status_code == 401


def test_out_of_range_directamente():
    assert out_of_range("temperatura", 20) is None
    assert out_of_range("temperatura", 100.1) is not None
    assert out_of_range("tipo_desconocido", 1e9) is None  # un tipo sin regla no se comprueba


def test_el_lote_de_historico_rechaza_todo_si_una_lectura_es_imposible():
    base = now() - timedelta(hours=2)
    lecturas = [{"timestamp": (base + timedelta(minutes=i)).isoformat(), "value": 20} for i in range(10)]
    lecturas[6]["value"] = 999
    r = client.post("/api/sensors/t001/data/batch", json={"readings": lecturas}, headers=KEY)
    assert r.status_code == 422 and "1 de 10" in r.json()["detail"] and "No se guardó nada" in r.json()["detail"]
    assert client.get("/api/sensors/t001/data", headers=auth()).json() == []
    lecturas[6]["value"] = 21
    assert client.post("/api/sensors/t001/data/batch", json={"readings": lecturas}, headers=KEY).status_code == 200


# ---------------------------------------------------------------- from y to


def carga(sensor, minutos_valores):
    body = {"readings": [{"timestamp": (now() - timedelta(minutes=m)).isoformat(), "value": v}
                         for m, v in minutos_valores]}
    assert client.post(f"/api/sensors/{sensor}/data/batch", json=body, headers=KEY).status_code == 200


def iso(minutos_atras):
    return (now() - timedelta(minutes=minutos_atras)).strftime("%Y-%m-%dT%H:%M:%SZ")


def datos(query):
    r = client.get(f"/api/sensors/t001/data?{query}", headers=auth("lector"))
    assert r.status_code == 200, r.text
    return [x["value"] for x in r.json()]


def test_from_y_to_filtran_una_ventana_incluidos_los_extremos():
    carga("t001", [(50, 1), (40, 2), (30, 3), (20, 4), (10, 5)])  # valores 1..5, de antiguo a reciente
    assert datos(f"from={iso(41)}&to={iso(19)}") == [2, 3, 4]
    assert datos(f"from={iso(31)}") == [3, 4, 5]
    assert datos(f"to={iso(29)}") == [1, 2, 3]
    assert datos("") == [1, 2, 3, 4, 5]


def test_los_extremos_exactos_estan_incluidos():
    carga("t001", [(30, 7)])
    exacta = client.get("/api/sensors/t001/data", headers=auth()).json()[0]["timestamp"]
    for query in (f"from={exacta}", f"to={exacta}", f"from={exacta}&to={exacta}"):
        assert datos(query) == [7], query


def test_con_limit_salen_las_mas_recientes_de_la_ventana_en_orden():
    carga("t001", [(m, 100 - m) for m in (60, 50, 40, 30, 20, 10)])
    assert datos(f"from={iso(55)}&limit=2") == [80, 90]  # las 2 más recientes, de antigua a reciente


def test_since_sigue_funcionando_y_se_combina_con_from_to():
    carga("t001", [(50, 1), (40, 2), (30, 3), (20, 4)])
    assert datos(f"since={iso(41)}") == [2, 3, 4]
    assert datos(f"since={iso(41)}&to={iso(21)}") == [2, 3]


def test_fechas_sin_zona_se_toman_como_utc_y_las_malas_o_al_reves_dan_422():
    carga("t001", [(30, 3)])
    sin_zona = (now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    assert datos(f"from={sin_zona}") == [3]
    h = auth()
    assert client.get("/api/sensors/t001/data?from=ayer", headers=h).status_code == 422
    assert client.get("/api/sensors/t001/data?to=ayer", headers=h).status_code == 422
    assert client.get(f"/api/sensors/t001/data?from={iso(10)}&to={iso(60)}", headers=h).status_code == 422


def test_data_sigue_trayendo_tipo_y_unidad_y_los_permisos():
    carga("t001", [(5, 20)])
    r = client.get("/api/sensors/t001/data", headers=auth("lector")).json()[0]
    assert (r["sensor_id"], r["type"]) == ("t001", "temperatura") and r["unit"]
    assert client.get("/api/sensors/t001/data").status_code == 401
    assert client.get("/api/sensors/zzz/data?from=2026-01-01T00:00:00Z", headers=auth()).status_code == 404


# ---------------------------------------------------------------- WebSocket por parcela


@pytest.fixture(autouse=True)
def rapido(monkeypatch):
    monkeypatch.setattr(routes, "WS_POLL_SECONDS", 0.05)


def ws(parcel_id=1, tok=None):
    return client.websocket_connect(f"/api/ws/parcels/{parcel_id}?token={tok if tok is not None else token()}")


def test_al_conectar_avisa_de_que_esta_lista():
    with ws() as c:
        assert c.receive_json() == {"type": "ready", "parcel_id": 1}


def test_una_lectura_llega_como_evento_reading_en_menos_de_2_segundos():
    with ws() as c:
        c.receive_json()
        t0 = time.monotonic()
        assert post("t001", 21.5).status_code == 200
        evento = c.receive_json()
        assert time.monotonic() - t0 < 2
    assert evento["type"] == "reading" and evento["parcel_id"] == 1
    d = evento["data"]
    assert (d["sensor_id"], d["value"], d["type"]) == ("t001", 21.5, "temperatura") and d["unit"]


def test_una_lectura_fuera_de_umbral_manda_reading_y_luego_alert():
    with ws() as c:
        c.receive_json()
        assert post("t001", 50).status_code == 200  # el máximo de t001 es 35
        primero, segundo = c.receive_json(), c.receive_json()
    assert (primero["type"], segundo["type"]) == ("reading", "alert")
    a = segundo["data"]
    assert (a["sensor_id"], a["type"], a["value"], a["threshold"]) == ("t001", "HIGH", 50, 35)
    assert a["resolved_at"] is None and a["acknowledged"] is False and segundo["parcel_id"] == 1


def test_no_se_repite_la_alerta_si_sigue_fuera_de_umbral():
    with ws() as c:
        c.receive_json()
        post("t001", 50, minutes_ago=2)
        post("t001", 51, minutes_ago=1)
        tipos = [c.receive_json()["type"] for _ in range(3)]
        c.send_text("ping")
        assert c.receive_json() == {"type": "pong"}
    assert tipos == ["reading", "alert", "reading"]  # la 2.ª lectura no abre otra alerta


def test_un_duplicado_y_una_lectura_rechazada_no_generan_evento():
    with ws() as c:
        c.receive_json()
        assert post("t001", 20, minutes_ago=5).status_code == 200
        c.receive_json()
        # mismo instante exacto: se guardó la primera, la segunda es duplicado y no avisa
        r = client.get("/api/sensors/t001/data", headers=auth()).json()[0]["timestamp"]
        dup = client.post("/api/sensors/t001/data", json={"value": 20, "timestamp": r}, headers=KEY)
        assert dup.json()["duplicate"] is True
        assert post("t001", 9999).status_code == 422
        c.send_text("ping")
        assert c.receive_json() == {"type": "pong"}  # lo siguiente es el pong, no un evento


def test_cada_parcela_recibe_lo_suyo():
    with ws(1) as uno, ws(2) as dos:
        uno.receive_json(), dos.receive_json()
        post("t002", 20)  # sensor de la finca 2
        assert dos.receive_json()["data"]["sensor_id"] == "t002"
        uno.send_text("ping")
        assert uno.receive_json() == {"type": "pong"}  # la 1 no recibió nada


def test_varios_clientes_de_la_misma_parcela_reciben_el_mismo_evento():
    with ws() as a, ws() as b:
        a.receive_json(), b.receive_json()
        post("t001", 20)
        assert a.receive_json()["data"]["value"] == b.receive_json()["data"]["value"] == 20


def test_el_historico_y_los_sensores_de_baja_no_se_retransmiten():
    with ws() as c:
        c.receive_json()
        body = {"readings": [{"timestamp": (now() - timedelta(hours=3)).isoformat(), "value": 20}]}
        assert client.post("/api/sensors/t001/data/batch", json=body, headers=KEY).status_code == 200
        client.patch("/api/sensors/h001", json={"is_active": False}, headers=auth())
        assert post("h001", 99).status_code == 200  # se guarda, pero ya no se retransmite
        c.send_text("ping")
        assert c.receive_json() == {"type": "pong"}


def test_sin_token_valido_o_parcela_que_no_existe_se_rechaza_con_1008():
    for intento in (lambda: ws(tok=""), lambda: ws(tok="basura"), lambda: ws(99)):
        with pytest.raises(WebSocketDisconnect) as e:
            with intento():
                pass
        assert e.value.code == 1008


def test_una_parcela_de_baja_solo_se_ve_siendo_admin_y_se_cierra_si_se_da_de_baja_en_directo():
    client.patch("/api/parcels/2", json={"is_active": False}, headers=auth())
    with pytest.raises(WebSocketDisconnect):
        with ws(2):
            pass
    with ws(2, token("admin")) as c:
        assert c.receive_json()["type"] == "ready"
    with ws(1) as c:  # el lector está en la parcela 1; se da de baja mientras escucha
        c.receive_json()
        client.patch("/api/parcels/1", json={"is_active": False}, headers=auth())
        with pytest.raises(WebSocketDisconnect) as e:
            c.receive_json()
        assert e.value.code == 1008


def test_al_desconectarse_el_cliente_se_borra_su_suscripcion():
    assert eventos.subscribers() == 0
    with ws() as c:
        c.receive_json()
        assert eventos.subscribers(1) == 1
    deadline = time.monotonic() + 2
    while eventos.subscribers() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert eventos.subscribers() == 0


def test_la_cola_de_un_cliente_lento_no_crece_sin_limite(monkeypatch):
    import asyncio

    monkeypatch.setattr(eventos, "QUEUE_SIZE", 3)

    async def scenario():
        sub = eventos.subscribe(7)
        for i in range(10):
            eventos.publish(7, {"n": i})
        await asyncio.sleep(0.05)
        out = [sub.queue.get_nowait()["n"] for _ in range(sub.queue.qsize())]
        eventos.unsubscribe(sub)
        return out

    assert asyncio.run(scenario()) == [7, 8, 9]  # se queda con lo más reciente
