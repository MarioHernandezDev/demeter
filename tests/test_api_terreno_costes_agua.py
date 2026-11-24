"""Terreno, costes, agua, predicción y riego desde la base de datos.

Seed: fincas 1, 2 y 3, con un depósito cada una (50 000, 20 000 y 30 000 l, con sensores de nivel
d001, d002 y d003) y sin zonas, elementos ni movimientos. Las lecturas se meten por la ingesta.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api
from demeter.api.geo import rectangle

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)
KEY = {"X-API-Key": "demo-ingest-key"}


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def post(sensor, value, minutes_ago=1):
    when = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
    r = client.post(f"/api/sensors/{sensor}/data", json={"value": value, "timestamp": when}, headers=KEY)
    assert r.status_code == 200


def zona(nombre="Bancal", tipo="crop", ancho=100, alto=50):
    return {"name": nombre, "type": tipo, "crop": "mango" if tipo == "crop" else None,
            "boundary": rectangle(36.7, -3.4, ancho, alto).model_dump()}


def baja(pid):
    assert client.patch(f"/api/parcels/{pid}", json={"is_active": False}, headers=auth()).status_code == 200


# ---------------------------------------------------------------- terreno


def test_terreno_de_las_tres_fincas_y_404():
    for pid in (1, 2, 3):
        t = client.get(f"/api/parcels/{pid}/terrain", headers=auth("lector")).json()
        assert t["parcel"]["id"] == pid and len(t["tanks"]) == 1 and t["zones"] == []
    assert client.get("/api/parcels/3/terrain", headers=auth("lector")).json()["sensors"][0]["parcel_id"] == 3
    assert client.get("/api/parcels/99/terrain", headers=auth()).status_code == 404


def test_crear_zona_se_guarda_calcula_el_area_y_sale_en_el_terreno():
    r = client.post("/api/parcels/3/zones", json=zona(), headers=auth("tecnico"))
    assert r.status_code == 201 and r.json()["area_m2"] == pytest.approx(5000, rel=0.02)
    t = client.get("/api/parcels/3/terrain", headers=auth("lector")).json()
    assert [z["name"] for z in t["zones"]] == ["Bancal"] and t["zones"][0]["id"] == r.json()["id"]
    assert client.get("/api/parcels/1/terrain", headers=auth()).json()["zones"] == []  # no se mezclan


def test_zona_permisos_404_422_y_parcela_de_baja():
    assert client.post("/api/parcels/1/zones", json=zona(), headers=auth("lector")).status_code == 403
    assert client.post("/api/parcels/99/zones", json=zona(), headers=auth()).status_code == 404
    malo = {**zona(), "boundary": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]}}
    assert client.post("/api/parcels/1/zones", json=malo, headers=auth()).status_code == 422
    baja(1)
    assert client.post("/api/parcels/1/zones", json=zona(), headers=auth()).status_code == 409
    assert client.post("/api/parcels/1/zones", json=zona(), headers=auth("tecnico")).status_code == 404


def test_elementos_se_guardan_y_se_borran_de_verdad():
    geom = {"type": "Point", "coordinates": [-3.69, 36.73]}
    body = {"type": "tree", "subtype": "mango", "geometry": geom, "height_m": 3}
    r = client.post("/api/parcels/2/elements", json=body, headers=auth("tecnico"))
    assert r.status_code == 201
    eid = r.json()["id"]
    assert [e["id"] for e in client.get("/api/parcels/2/terrain", headers=auth()).json()["elements"]] == [eid]
    assert client.delete(f"/api/elements/{eid}", headers=auth("tecnico")).status_code == 204
    assert client.get("/api/parcels/2/terrain", headers=auth()).json()["elements"] == []
    assert client.delete(f"/api/elements/{eid}", headers=auth("tecnico")).status_code == 404  # ya no existe
    assert client.delete("/api/elements/1", headers=auth("lector")).status_code == 403


def test_elemento_con_datos_malos_o_en_parcela_inexistente():
    geom = {"type": "Point", "coordinates": [-3.69, 36.73]}
    body = {"type": "tree", "geometry": geom}
    assert client.post("/api/parcels/99/elements", json=body, headers=auth()).status_code == 404
    assert client.post("/api/parcels/1/elements", json={**body, "type": "roca"}, headers=auth()).status_code == 422
    assert client.post("/api/parcels/1/elements", json={**body, "height_m": -1}, headers=auth()).status_code == 422


def test_un_lector_no_ve_en_el_terreno_los_sensores_desactivados():
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth())
    ids = lambda role: {x["id"] for x in client.get("/api/parcels/1/terrain", headers=auth(role)).json()["sensors"]}
    assert "t001" not in ids("lector") and "t001" in ids("tecnico")


def test_terreno_de_una_parcela_de_baja_solo_para_admin():
    baja(2)
    assert client.get("/api/parcels/2/terrain", headers=auth("lector")).status_code == 404
    t = client.get("/api/parcels/2/terrain", headers=auth("admin")).json()
    assert t["parcel"]["is_active"] is False


# ---------------------------------------------------------------- costes


def apunte(kind, category, amount, dia="2026-11-01", **extra):
    return {"kind": kind, "category": category, "amount": amount, "occurred_on": dia, **extra}


def test_apuntar_movimientos_listar_y_balance():
    h = auth("tecnico")
    for body in (apunte("income", "venta", 1000), apunte("expense", "agua", 100.10, "2026-11-05"),
                 apunte("expense", "agua", 20.05, "2026-11-03"), apunte("income", "agua", 20, "2026-11-04")):
        assert client.post("/api/parcels/3/transactions", json=body, headers=h).status_code == 201
    lista = client.get("/api/parcels/3/transactions", headers=auth("lector")).json()
    assert [x["occurred_on"] for x in lista] == ["2026-11-05", "2026-11-04", "2026-11-03", "2026-11-01"]
    b = client.get("/api/parcels/3/balance", headers=auth("lector")).json()
    assert (b["income"], b["expense"], b["balance"]) == (1020.0, 120.15, 899.85)
    assert b["by_category"] == {"agua": -100.15, "venta": 1000.0}
    assert client.get("/api/parcels/1/balance", headers=auth()).json()["balance"] == 0  # no se mezclan


def test_costes_validacion_permisos_y_parcela_de_baja():
    assert client.post("/api/parcels/1/transactions", json=apunte("income", "venta", 1), headers=auth("lector")).status_code == 403
    assert client.post("/api/parcels/99/transactions", json=apunte("income", "venta", 1), headers=auth()).status_code == 404
    for malo in (apunte("income", "venta", 0), apunte("income", "venta", -5), apunte("otro", "venta", 1),
                 apunte("income", "", 1), apunte("income", "venta", 1, dia="ayer")):
        assert client.post("/api/parcels/1/transactions", json=malo, headers=auth()).status_code == 422
    baja(1)
    assert client.post("/api/parcels/1/transactions", json=apunte("income", "venta", 1), headers=auth()).status_code == 409
    assert client.get("/api/parcels/1/transactions", headers=auth("lector")).status_code == 404
    assert client.get("/api/parcels/1/balance", headers=auth("admin")).status_code == 200
    assert client.get("/api/parcels/99/balance", headers=auth()).status_code == 404


# ---------------------------------------------------------------- agua


def test_agua_sin_lecturas_no_se_sabe_el_nivel():
    w = client.get("/api/parcels/3/water", headers=auth("lector")).json()
    assert w["total_capacity_l"] == 30000 and w["available_l"] == 0
    assert w["tanks"][0]["level_pct"] is None and w["tanks"][0]["available_l"] is None


def test_agua_sale_del_ultimo_valor_del_sensor_del_deposito():
    post("d003", 20, minutes_ago=30)
    post("d003", 50, minutes_ago=2)  # el más reciente manda
    w = client.get("/api/parcels/3/water", headers=auth("lector")).json()
    assert w["tanks"][0]["level_pct"] == 50 and w["available_l"] == 15000 and w["level_pct"] == 50


def test_el_reparto_es_proporcional_a_la_superficie_de_cultivo():
    post("d003", 100)
    client.post("/api/parcels/3/zones", json=zona("Grande", ancho=200, alto=50), headers=auth())
    client.post("/api/parcels/3/zones", json=zona("Pequeña", ancho=100, alto=50), headers=auth())
    client.post("/api/parcels/3/zones", json=zona("Camino", "no_crop"), headers=auth())  # no cuenta
    d = client.get("/api/parcels/3/water", headers=auth()).json()["distribution"]
    assert {x["zone_name"]: x["share_pct"] for x in d} == {"Grande": pytest.approx(66.7, abs=0.1),
                                                           "Pequeña": pytest.approx(33.3, abs=0.1)}
    assert sum(x["liters"] for x in d) == pytest.approx(30000, abs=0.2)


def test_agua_404_baja_y_el_dashboard_la_lleva_de_la_bd():
    assert client.get("/api/parcels/99/water", headers=auth()).status_code == 404
    post("d003", 40)
    dash = client.get("/api/dashboard?parcel_id=3", headers=auth()).json()
    assert dash["water"]["available_l"] == 12000 and dash["water"]["tanks"][0]["name"] == "Balsa de riego"
    baja(3)
    assert client.get("/api/parcels/3/water", headers=auth("lector")).status_code == 404


# ---------------------------------------------------------------- predicción y riego


def serie(sensor, valores, cada=10):
    ahora = datetime.now(timezone.utc)
    cuerpo = {"readings": [{"timestamp": (ahora - timedelta(minutes=cada * (len(valores) - i))).isoformat(),
                            "value": v} for i, v in enumerate(valores)]}
    assert client.post(f"/api/sensors/{sensor}/data/batch", json=cuerpo, headers=KEY).status_code == 200


def test_prediccion_sin_datos_404_y_con_datos_24_puntos():
    assert client.get("/api/sensors/t001/prediction", headers=auth()).status_code == 404
    serie("t001", [20 + (i % 6) * 0.5 for i in range(200)], cada=10)  # ~33 h de datos
    r = client.get("/api/sensors/t001/prediction", headers=auth("lector"))
    assert r.status_code == 200 and len(r.json()["points"]) == 24 and r.json()["sensor_id"] == "t001"


def test_prediccion_permisos_404_y_sensor_de_baja():
    assert client.get("/api/sensors/t001/prediction").status_code == 401
    assert client.get("/api/sensors/zzz/prediction", headers=auth()).status_code == 404
    serie("t001", [20 + (i % 6) * 0.5 for i in range(200)], cada=10)
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth())
    assert client.get("/api/sensors/t001/prediction", headers=auth("lector")).status_code == 404
    assert client.get("/api/sensors/t001/prediction", headers=auth("tecnico")).status_code == 200


def test_riego_de_una_finca_sin_datos_es_valido_y_no_pide_agua():
    a = client.get("/api/parcels/3/irrigation", headers=auth("lector"))
    assert a.status_code == 200
    d = a.json()
    assert d["action"] in ("irrigate", "wait", "skip") and d["summary"] and d["total_liters"] == 0


@pytest.fixture
def con_clima(monkeypatch):
    """Internet falso con un clima sin lluvia (la previsión que pide el consejo de riego)."""
    from demeter.services import weather

    def falso(latitude, longitude):
        inicio = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
        horas = [(inicio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(30)]
        return {"current": {"temperature_2m": 22, "relative_humidity_2m": 50, "wind_speed_10m": 5,
                            "precipitation": 0, "weather_code": 0},
                "hourly": {"time": horas, "temperature_2m": [14 + (i % 24) for i in range(30)],
                           "precipitation_probability": [0] * 30, "precipitation": [0] * 30}}

    monkeypatch.setattr(weather, "_fetch_json", falso)


def test_riego_sin_prevision_del_tiempo_espera_en_vez_de_regar_a_ciegas():
    post("d003", 80)
    post("h003", 10)
    client.post("/api/parcels/3/zones", json=zona("Tomates"), headers=auth())
    d = client.get("/api/parcels/3/irrigation", headers=auth("lector")).json()  # sin internet
    assert d["action"] == "wait" and "previsión" in d["summary"]


def test_riego_con_suelo_seco_zonas_y_agua_recomienda_regar(con_clima):
    post("d003", 80)  # depósito casi lleno
    post("h003", 10)  # suelo muy seco (el mínimo es 25 %)
    client.post("/api/parcels/3/zones", json=zona("Tomates"), headers=auth())
    # el sensor de humedad hay que colocarlo dentro de la zona para que el consejo lo asigne a ella
    client.patch("/api/sensors/h003", json={"latitude": 36.7, "longitude": -3.4}, headers=auth("tecnico"))
    d = client.get("/api/parcels/3/irrigation", headers=auth("lector")).json()
    assert d["factors"]["soil_moisture_pct"] == 10 and d["available_l"] == 24000
    assert d["action"] == "irrigate" and d["zones"] and d["zones"][0]["zone_name"] == "Tomates"
    assert d["total_liters"] <= d["available_l"]


def test_riego_404_baja_y_permisos():
    assert client.get("/api/parcels/99/irrigation", headers=auth()).status_code == 404
    assert client.get("/api/parcels/1/irrigation").status_code == 401
    baja(1)
    assert client.get("/api/parcels/1/irrigation", headers=auth("lector")).status_code == 404
