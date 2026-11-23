"""Pruebas del contrato de la API (issue #20): forma de las respuestas, permisos y validación."""

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api
from demeter.api.geo import polygon_area_m2, rectangle
from demeter.state.types import DashboardSummary as UiDashboard  # contrato de la interfaz

client = TestClient(api)


_tokens: dict = {}


def auth(role="admin"):
    """Cabecera con un token real (JWT) de uno de los usuarios de ejemplo."""
    if role not in _tokens:
        r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
        _tokens[role] = r.json()["access_token"]
    return {"Authorization": f"Bearer {_tokens[role]}"}


def test_health():
    assert client.get("/api/health").json()["status"] == "ok"


def test_login_ok_y_mal():
    r = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    assert client.post("/api/auth/login", json={"username": "admin", "password": "x"}).status_code == 401


def test_sin_token_401():
    assert client.get("/api/parcels").status_code == 401


def test_dashboard_lo_entiende_la_interfaz():
    r = client.get("/api/dashboard", headers=auth("lector"))
    assert r.status_code == 200
    ui = UiDashboard.from_api(r.json())  # el tipo que ya usa la interfaz
    assert ui.sensors and ui.parcel.name


def test_sensores_y_umbrales_solo_admin():
    assert len(client.get("/api/parcels/1/sensors", headers=auth()).json()) == 6
    body = {"threshold_high": 40}
    assert client.patch("/api/sensors/t001", json=body, headers=auth("tecnico")).status_code == 403
    assert client.patch("/api/sensors/t001", json=body, headers=auth("admin")).json()["threshold_high"] == 40
    colocar = {"latitude": 36.7, "longitude": -3.4}
    assert client.patch("/api/sensors/t001", json=colocar, headers=auth("tecnico")).status_code == 200


def test_lector_no_escribe():
    r = client.post("/api/parcels/1/transactions", headers=auth("lector"),
                    json={"kind": "expense", "category": "agua", "amount": 10, "occurred_on": "2026-11-01"})
    assert r.status_code == 403


def test_lecturas_y_limit():
    r = client.get("/api/sensors/t001/data?limit=5", headers=auth())
    assert len(r.json()) == 5 and r.json()[0]["sensor_id"] == "t001"
    assert client.get("/api/sensors/zzz/data", headers=auth()).status_code == 404


def test_ingesta_necesita_api_key():
    body = {"timestamp": "2026-11-16T10:00:00Z", "value": 21.5}
    assert client.post("/api/sensors/t001/data", json=body).status_code == 401
    r = client.post("/api/sensors/t001/data", json=body, headers={"X-API-Key": "demo-ingest-key"})
    assert r.status_code == 200 and r.json()["stored"] is True


def test_terreno_completo():
    t = client.get("/api/parcels/1/terrain", headers=auth()).json()
    assert {"parcel", "zones", "elements", "sensors", "tanks"} <= t.keys()
    assert {e["type"] for e in t["elements"]} == {"tree", "terrace", "path"}
    assert t["parcel"]["boundary"]["type"] == "Polygon"


def test_zona_calcula_area():
    poly = rectangle(36.7, -3.4, 100, 50).model_dump()
    r = client.post("/api/parcels/1/zones", headers=auth("tecnico"),
                    json={"name": "Nueva", "type": "crop", "crop": "mango", "boundary": poly})
    assert r.status_code == 201 and r.json()["area_m2"] == pytest.approx(5000, rel=0.01)


def test_area_rectangulo():
    assert polygon_area_m2(rectangle(36.72, -3.43, 200, 100)) == pytest.approx(20000, rel=0.005)


def test_agua_y_balance():
    w = client.get("/api/parcels/1/water", headers=auth()).json()
    assert w["available_l"] == pytest.approx(sum(t["available_l"] for t in w["tanks"]), abs=0.2)
    assert sum(x["share_pct"] for x in w["distribution"]) == pytest.approx(100, abs=0.2)
    b = client.get("/api/parcels/1/balance", headers=auth()).json()
    assert b["balance"] == pytest.approx(b["income"] - b["expense"])


def test_validacion_422():
    r = client.post("/api/parcels/1/transactions", headers=auth(),
                    json={"kind": "expense", "category": "agua", "amount": -5, "occurred_on": "2026-11-01"})
    assert r.status_code == 422


def test_openapi_expone_todo():
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/dashboard", "/api/parcels/{parcel_id}/terrain", "/api/sensors/{sensor_id}/data",
              "/api/alerts/{alert_id}", "/api/auth/login"]:
        assert p in paths


def test_prediccion_24h():
    r = client.get("/api/sensors/t001/prediction", headers=auth("lector"))
    assert r.status_code == 200
    p = r.json()
    assert p["horizon_hours"] == 24 and p["step_minutes"] == 60 and len(p["points"]) == 24
    assert all(x["lower"] <= x["value"] <= x["upper"] for x in p["points"])
    assert p["points"][0]["time"] < p["points"][-1]["time"]
    assert p["trend"] in ("rising", "falling", "stable")
    assert client.get("/api/sensors/zzz/prediction", headers=auth()).status_code == 404
    assert client.get("/api/sensors/t001/prediction").status_code == 401


def test_prediccion_avisa_de_cruce_de_umbral():
    # h002 está dentro de umbrales y h001 ya fuera: solo el primero puede tener ``crossing``.
    for sid in ("t001", "h001", "h002", "d001"):
        p = client.get(f"/api/sensors/{sid}/prediction", headers=auth()).json()
        if p["crossing"]:
            assert p["crossing"]["type"] in ("LOW", "HIGH")
            assert p["crossing"]["at"] in [x["time"] for x in p["points"]]


def test_consejo_de_riego():
    r = client.get("/api/parcels/1/irrigation", headers=auth("lector"))
    assert r.status_code == 200
    a = r.json()
    assert a["action"] in ("irrigate", "wait", "skip") and a["summary"]
    assert a["enough_water"] == (a["available_l"] >= a["total_liters"])
    if a["action"] == "irrigate":
        assert a["zones"] and a["total_liters"] == pytest.approx(sum(z["liters"] for z in a["zones"]), abs=0.2)
    else:
        assert a["zones"] == [] and a["total_liters"] == 0
    assert client.get("/api/parcels/99/irrigation", headers=auth()).status_code == 404
