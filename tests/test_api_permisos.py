"""Pruebas transversales de la API (A8, issue #26): permisos de TODAS las rutas, tokens y el resto.

La tabla de permisos se recorre contra ``/openapi.json``: si alguien añade una ruta que no es de
lectura y no la declara aquí, ``test_toda_ruta_de_escritura_esta_clasificada`` falla. Así ninguna
ruta nueva se queda sin pensar quién puede usarla.
"""

import time
import warnings
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from demeter.api import security
from demeter.api.app import api
from demeter.api.geo import rectangle

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)

PUBLIC = {("GET", "/api/health"), ("POST", "/api/auth/login")}
INGEST_KEY = {("POST", "/api/sensors/{sensor_id}/data"), ("POST", "/api/sensors/{sensor_id}/data/batch")}
ADMIN = {
    ("GET", "/api/users"), ("POST", "/api/users"), ("PATCH", "/api/users/{user_id}"),
    ("PATCH", "/api/parcels/{parcel_id}"),
}
EDITOR = {
    ("PUT", "/api/parcels/{parcel_id}/boundary"), ("PATCH", "/api/sensors/{sensor_id}"),
    ("POST", "/api/parcels/{parcel_id}/zones"), ("POST", "/api/parcels/{parcel_id}/elements"),
    ("DELETE", "/api/elements/{element_id}"), ("POST", "/api/parcels/{parcel_id}/transactions"),
    ("PATCH", "/api/alerts/{alert_id}"), ("POST", "/api/alerts/ack-all"),
}
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def all_routes():
    out = []
    for path, methods in api.openapi()["paths"].items():
        for method in methods:
            out.append((method.upper(), path))
    return sorted(out)


def concrete(path):
    """Rellena los parámetros de la ruta con valores que existen en el seed."""
    for name, value in {"parcel_id": "1", "sensor_id": "t001", "user_id": "1", "alert_id": "1",
                        "element_id": "1", "zone_id": "1"}.items():
        path = path.replace("{" + name + "}", value)
    if path.endswith("/alerts/ack-all"):
        path += "?parcel_id=1"
    return path


def call(method, path, headers=None):
    if (method, path) in INGEST_KEY:  # cuerpo válido, para que lo único que falle sea la clave
        body = {"readings": [{"timestamp": "2026-01-01T00:00:00Z", "value": 1}]} if path.endswith("/batch") else {"value": 1}
    else:
        body = {} if method in WRITE_METHODS else None
    return client.request(method, concrete(path), headers=headers or {}, json=body)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# ---------------------------------------------------------------- la tabla de permisos


def test_toda_ruta_de_escritura_esta_clasificada():
    conocidas = PUBLIC | INGEST_KEY | ADMIN | EDITOR
    sin_clasificar = [(m, p) for m, p in all_routes() if m in WRITE_METHODS and (m, p) not in conocidas]
    assert sin_clasificar == [], f"Rutas de escritura sin permisos declarados: {sin_clasificar}"


def test_la_tabla_no_nombra_rutas_que_ya_no_existen():
    existentes = set(all_routes())
    assert (PUBLIC | INGEST_KEY | ADMIN | EDITOR) <= existentes


@pytest.mark.parametrize("method,path", [r for r in all_routes() if r not in PUBLIC | INGEST_KEY])
def test_sin_token_401(method, path):
    assert call(method, path).status_code == 401


@pytest.mark.parametrize("method,path", sorted(ADMIN | EDITOR))
def test_un_lector_no_puede_escribir(method, path):
    assert call(method, path, auth("lector")).status_code == 403


@pytest.mark.parametrize("method,path", sorted(ADMIN))
def test_un_tecnico_no_puede_hacer_lo_del_admin(method, path):
    assert call(method, path, auth("tecnico")).status_code == 403


@pytest.mark.parametrize("method,path", sorted(INGEST_KEY))
def test_la_ingesta_no_acepta_un_token_de_usuario(method, path):
    # ni siquiera el de un admin: la ingesta solo entiende la X-API-Key
    assert call(method, path, auth("admin")).status_code == 401


@pytest.mark.parametrize("method,path", [r for r in all_routes() if r[0] == "GET" and r not in PUBLIC | ADMIN])
def test_un_lector_puede_leer_todo_lo_que_es_de_lectura(method, path):
    assert call(method, path, auth("lector")).status_code in (200, 404, 503)  # 404: ese id no existe; 503: clima sin internet


# ---------------------------------------------------------------- tokens


def test_token_caducado_manipulado_y_con_otro_algoritmo():
    uid = client.post("/api/auth/login", json={"username": "admin", "password": "demo1234"}).json()["user"]["id"]
    ok = security.create_access_token(uid)
    caducado = security.create_access_token(uid, minutes=-1)
    manipulado = ok[:-3] + ("AAA" if not ok.endswith("AAA") else "BBB")
    otra_clave = jwt.encode({"sub": str(uid), "exp": time.time() + 600}, "otra-clave-distinta-de-32-bytes!!", algorithm="HS256")
    sin_firma = jwt.encode({"sub": str(uid), "exp": time.time() + 600}, None, algorithm="none")
    sin_exp = jwt.encode({"sub": str(uid)}, security.JWT_SECRET, algorithm="HS256")
    sub_raro = jwt.encode({"sub": "abc", "exp": time.time() + 600}, security.JWT_SECRET, algorithm="HS256")
    usuario_inexistente = security.create_access_token(9999)

    def status(token):
        return client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code

    assert status(ok) == 200
    for malo in (caducado, manipulado, otra_clave, sin_firma, sin_exp, sub_raro, usuario_inexistente, "", "x.y.z"):
        assert status(malo) == 401, malo


def test_cabecera_authorization_mal_formada():
    token = auth()["Authorization"].split()[1]
    for header in (token, f"Basic {token}", "Bearer", "Bearer  ", f"Token {token}"):
        assert client.get("/api/auth/me", headers={"Authorization": header}).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": f"bearer {token}"}).status_code == 200


def test_login_casos_raros():
    def login(body):
        return client.post("/api/auth/login", json=body).status_code
    assert login({"username": "nadie", "password": "demo1234"}) == 401
    assert login({"username": "admin", "password": "x" * 100}) == 401  # pasa de 72 bytes
    assert login({"username": "admin", "password": "é" * 40}) == 401  # 80 bytes
    assert login({"username": "admin"}) == 422 and login({}) == 422
    assert login({"username": "", "password": "demo1234"}) == 422


def test_el_secreto_de_ejemplo_avisa_y_no_se_usa(monkeypatch):
    monkeypatch.setenv("DEMETER_JWT_SECRET", "cambia-esto-en-produccion")
    with pytest.warns(UserWarning, match="valor de ejemplo"):
        secreto = security._load_secret()
    assert secreto != "cambia-esto-en-produccion" and len(secreto) >= 32
    monkeypatch.setenv("DEMETER_JWT_SECRET", "uno-propio-de-verdad-" * 3)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert security._load_secret().startswith("uno-propio")


# ---------------------------------------------------------------- terreno, clima, agua y costes


def test_clima_y_agua_de_las_tres_fincas_y_404():
    for pid in (1, 2, 3):
        assert client.get(f"/api/parcels/{pid}/water", headers=auth("lector")).status_code == 200
        # el clima es real: sin internet (las pruebas no tienen) la API lo dice con un 503 claro
        assert client.get(f"/api/parcels/{pid}/weather", headers=auth("lector")).status_code == 503
    assert client.get("/api/parcels/99/weather", headers=auth()).status_code == 404
    assert client.get("/api/parcels/99/water", headers=auth()).status_code == 404


def test_elementos_del_terreno_crear_y_borrar():
    h = auth("tecnico")
    geom = {"type": "Point", "coordinates": [-3.69, 36.73]}
    body = {"type": "tree", "subtype": "mango", "geometry": geom, "height_m": 3}
    r = client.post("/api/parcels/1/elements", json=body, headers=h)
    assert r.status_code == 201 and r.json()["parcel_id"] == 1
    assert client.post("/api/parcels/99/elements", json=body, headers=h).status_code == 404
    assert client.post("/api/parcels/1/elements", json={**body, "height_m": -1}, headers=h).status_code == 422
    terreno = client.get("/api/parcels/1/terrain", headers=h).json()
    eid = terreno["elements"][0]["id"]
    assert client.delete(f"/api/elements/{eid}", headers=h).status_code == 204
    assert client.delete("/api/elements/999999", headers=h).status_code == 404


def test_zona_con_poligono_malo_o_en_parcela_inexistente():
    h = auth("tecnico")
    ok = {"name": "Z", "type": "crop", "crop": "mango", "boundary": rectangle(36.7, -3.4, 50, 50).model_dump()}
    assert client.post("/api/parcels/1/zones", json=ok, headers=h).status_code == 201
    assert client.post("/api/parcels/99/zones", json=ok, headers=h).status_code == 404
    malo = {**ok, "boundary": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]}}
    assert client.post("/api/parcels/1/zones", json=malo, headers=h).status_code == 422


def test_costes_listar_crear_y_validar():
    h = auth("tecnico")
    assert client.get("/api/parcels/1/transactions", headers=auth("lector")).status_code == 200
    assert client.get("/api/parcels/99/transactions", headers=h).status_code == 404
    body = {"kind": "income", "category": "venta", "amount": 120.5, "occurred_on": "2026-11-01"}
    assert client.post("/api/parcels/1/transactions", json=body, headers=h).status_code == 201
    assert client.post("/api/parcels/99/transactions", json=body, headers=h).status_code == 404
    for malo in ({**body, "amount": 0}, {**body, "kind": "otro"}, {**body, "category": ""},
                 {**body, "occurred_on": "ayer"}):
        assert client.post("/api/parcels/1/transactions", json=malo, headers=h).status_code == 422


def test_respuestas_de_error_no_enseñan_el_valor_enviado():
    r = client.post("/api/auth/login", json={"username": "admin", "password": 123456})
    assert r.status_code == 422 and "123456" not in r.text
