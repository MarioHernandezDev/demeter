"""Pruebas de las rutas de parcelas y sensores contra la base de datos (A4, issue #22).

Cada prueba usa una base de datos en memoria nueva con los datos del seed (``api_db``):
3 fincas (id 1, 2 y 3) y 14 sensores (5 + 5 + 4).
"""

import pytest
from fastapi.testclient import TestClient

from demeter.api.app import api
from demeter.api.geo import rectangle
from demeter.db import conexion

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def baja(parcel_id, active=False, role="admin"):
    return client.patch(f"/api/parcels/{parcel_id}", json={"is_active": active}, headers=auth(role))


# ---------------------------------------------------------------- listar y ver parcelas


def test_lista_las_tres_fincas_del_seed():
    parcels = client.get("/api/parcels", headers=auth("lector")).json()
    assert [p["name"] for p in parcels] == ["Finca La Costa", "Huerta del Río", "Vega de Motril"]
    assert all(p["is_active"] for p in parcels)


def test_detalle_de_una_parcela_y_404():
    p = client.get("/api/parcels/1", headers=auth("lector")).json()
    assert p["name"] == "Finca La Costa" and p["boundary"] is None
    assert client.get("/api/parcels/99", headers=auth()).status_code == 404


def test_parcelas_exigen_token():
    assert client.get("/api/parcels").status_code == 401
    assert client.patch("/api/parcels/1", json={"is_active": False}).status_code == 401


# ---------------------------------------------------------------- baja y reactivación


def test_dar_de_baja_oculta_la_parcela_a_quien_no_es_admin():
    assert baja(2).json()["is_active"] is False
    assert [p["id"] for p in client.get("/api/parcels", headers=auth("lector")).json()] == [1, 3]
    assert client.get("/api/parcels/2", headers=auth("lector")).status_code == 404
    assert client.get("/api/parcels/2", headers=auth("tecnico")).status_code == 404
    # el admin sí la ve, marcada como de baja
    assert client.get("/api/parcels/2", headers=auth()).json()["is_active"] is False


def test_admin_ve_las_de_baja_con_include_inactive_y_puede_reactivarlas():
    baja(2)
    todas = client.get("/api/parcels?include_inactive=true", headers=auth()).json()
    assert {p["id"]: p["is_active"] for p in todas} == {1: True, 2: False, 3: True}
    assert baja(2, active=True).json()["is_active"] is True
    assert [p["id"] for p in client.get("/api/parcels", headers=auth("lector")).json()] == [1, 2, 3]


@pytest.mark.parametrize("role", ["tecnico", "lector"])
def test_include_inactive_y_la_baja_son_solo_de_admin(role):
    assert client.get("/api/parcels?include_inactive=true", headers=auth(role)).status_code == 403
    assert baja(1, role=role).status_code == 403


def test_baja_de_una_parcela_que_no_existe():
    assert baja(99).status_code == 404


def test_la_baja_desactiva_todos_sus_sensores_y_la_reactivacion_los_reactiva():
    baja(1)
    sensores = client.get("/api/parcels/1/sensors", headers=auth()).json()
    assert len(sensores) == 5 and not any(x["is_active"] for x in sensores)
    # los de otras parcelas no se tocan
    assert all(x["is_active"] for x in client.get("/api/parcels/2/sensors", headers=auth()).json())
    baja(1, active=True)
    assert all(x["is_active"] for x in client.get("/api/parcels/1/sensors", headers=auth()).json())


# ---------------------------------------------------------------- contorno


def test_guardar_contorno_calcula_el_area_y_se_conserva():
    boundary = rectangle(36.73, -3.69, 100, 50).model_dump()
    r = client.put("/api/parcels/1/boundary", json={"boundary": boundary}, headers=auth("tecnico"))
    assert r.status_code == 200
    assert r.json()["area_m2"] == pytest.approx(5000, rel=0.02)
    again = client.get("/api/parcels/1", headers=auth("lector")).json()
    assert again["boundary"]["type"] == "Polygon" and again["area_m2"] == r.json()["area_m2"]


def test_contorno_lector_403_inexistente_404_y_malo_422():
    boundary = rectangle(36.73, -3.69, 100, 50).model_dump()
    assert client.put("/api/parcels/1/boundary", json={"boundary": boundary}, headers=auth("lector")).status_code == 403
    assert client.put("/api/parcels/99/boundary", json={"boundary": boundary}, headers=auth()).status_code == 404
    bad = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]}
    assert client.put("/api/parcels/1/boundary", json={"boundary": bad}, headers=auth()).status_code == 422


def test_no_se_edita_el_contorno_de_una_parcela_de_baja():
    baja(1)
    boundary = rectangle(36.73, -3.69, 100, 50).model_dump()
    r = client.put("/api/parcels/1/boundary", json={"boundary": boundary}, headers=auth())
    assert r.status_code == 409


# ---------------------------------------------------------------- sensores


def test_lista_de_sensores_de_cada_finca():
    counts = [len(client.get(f"/api/parcels/{i}/sensors", headers=auth()).json()) for i in (1, 2, 3)]
    assert counts == [5, 5, 4]
    s0 = client.get("/api/parcels/1/sensors", headers=auth()).json()[0]
    assert {"id", "parcel_id", "type", "unit", "threshold_low", "threshold_high", "is_active"} <= s0.keys()
    assert client.get("/api/parcels/99/sensors", headers=auth()).status_code == 404


def test_el_lector_no_ve_los_sensores_desactivados_pero_el_tecnico_si():
    client.patch("/api/sensors/t001", json={"is_active": False}, headers=auth("tecnico"))
    ids = lambda role: {x["id"] for x in client.get("/api/parcels/1/sensors", headers=auth(role)).json()}
    assert "t001" not in ids("lector")
    assert "t001" in ids("tecnico") and "t001" in ids("admin")


def test_umbrales_los_cambia_solo_el_admin():
    body = {"threshold_low": 10, "threshold_high": 30}
    assert client.patch("/api/sensors/t001", json=body, headers=auth("tecnico")).status_code == 403
    assert client.patch("/api/sensors/t001", json=body, headers=auth("lector")).status_code == 403
    r = client.patch("/api/sensors/t001", json=body, headers=auth("admin"))
    assert r.status_code == 200 and (r.json()["threshold_low"], r.json()["threshold_high"]) == (10, 30)


def test_minimo_menor_que_maximo_tambien_contra_lo_guardado():
    # t001 tiene umbral mínimo 8 y máximo 35 (seed)
    assert client.patch("/api/sensors/t001", json={"threshold_high": 5}, headers=auth()).status_code == 422
    assert client.patch("/api/sensors/t001", json={"threshold_low": 40}, headers=auth()).status_code == 422
    assert client.patch("/api/sensors/t001", json={"threshold_low": 20, "threshold_high": 20}, headers=auth()).status_code == 422
    # nada se guardó con los intentos malos
    s0 = next(x for x in client.get("/api/parcels/1/sensors", headers=auth()).json() if x["id"] == "t001")
    assert (s0["threshold_low"], s0["threshold_high"]) == (8, 35)


def test_null_quita_un_umbral_y_lo_ausente_no_se_toca():
    r = client.patch("/api/sensors/t001", json={"threshold_high": None}, headers=auth()).json()
    assert r["threshold_high"] is None and r["threshold_low"] == 8
    r = client.patch("/api/sensors/t001", json={"latitude": 36.7}, headers=auth("tecnico")).json()
    assert r["latitude"] == 36.7 and r["threshold_high"] is None  # sigue sin máximo


def test_colocar_el_sensor_valida_las_coordenadas():
    ok = client.patch("/api/sensors/t001", json={"latitude": 36.7, "longitude": -3.4}, headers=auth("tecnico"))
    assert ok.status_code == 200 and ok.json()["longitude"] == -3.4
    assert client.patch("/api/sensors/t001", json={"latitude": 95}, headers=auth()).status_code == 422
    assert client.patch("/api/sensors/t001", json={"longitude": -200}, headers=auth()).status_code == 422


def test_is_active_no_admite_null_y_un_cuerpo_vacio_no_cambia_nada():
    assert client.patch("/api/sensors/t001", json={"is_active": None}, headers=auth()).status_code == 422
    antes = client.get("/api/parcels/1/sensors", headers=auth()).json()
    assert client.patch("/api/sensors/t001", json={}, headers=auth()).status_code == 200
    assert client.get("/api/parcels/1/sensors", headers=auth()).json() == antes


def test_sensor_inexistente_404():
    assert client.patch("/api/sensors/zzz", json={"is_active": False}, headers=auth()).status_code == 404


def test_no_se_reactiva_un_sensor_de_una_parcela_de_baja():
    baja(1)
    r = client.patch("/api/sensors/t001", json={"is_active": True}, headers=auth())
    assert r.status_code == 409
    # un técnico ni siquiera ve la parcela de baja
    assert client.patch("/api/sensors/t001", json={"is_active": True}, headers=auth("tecnico")).status_code == 404


# ---------------------------------------------------------------- sin base de datos


def test_sin_base_de_datos_preparada_avisa_con_503_y_dice_que_hacer(monkeypatch):
    # motor en memoria SIN tablas: lo que pasa si nadie ha ejecutado ``reflex db migrate``
    monkeypatch.setattr(conexion, "_engine", conexion.make_engine("sqlite://"))
    r = client.get("/api/parcels", headers=auth())
    assert r.status_code == 503
    assert "reflex db migrate" in r.json()["detail"]
