"""Pruebas del login real (A3, issue #21): bcrypt, JWT, caducidad, bajas y permisos por rol."""

import time

import jwt
import pytest
from fastapi.testclient import TestClient

from demeter.api import security
from demeter.api import schemas as s
from demeter.api.app import api
from demeter.api.geo import rectangle
from demeter.api.auth import DemoUserStore, StoredUser, get_user_store

client = TestClient(api)


def login(username="admin", password="demo1234"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------- contraseñas


def test_bcrypt_hash_y_verificacion():
    h = security.hash_password("clave-segura-1")
    assert h != "clave-segura-1" and h.startswith("$2")
    assert security.verify_password("clave-segura-1", h)
    assert not security.verify_password("otra", h)
    # misma contraseña, dos huellas distintas (cada una lleva su sal)
    assert security.hash_password("clave-segura-1") != h


def test_contrasena_demasiado_larga_se_rechaza_no_se_recorta():
    with pytest.raises(ValueError):
        security.hash_password("a" * 73)
    h = security.hash_password("a" * 72)
    assert not security.verify_password("a" * 73, h)
    assert not security.verify_password("x", "no-es-una-huella")


# ---------------------------------------------------------------- login


def test_login_devuelve_jwt_con_id_y_caducidad_sin_rol():
    r = login()
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer" and body["user"]["username"] == "admin"
    claims = jwt.decode(body["access_token"], security.JWT_SECRET, algorithms=["HS256"])
    assert claims["sub"] == "1" and claims["exp"] > time.time()
    assert "role" not in claims and "password" not in str(claims)


@pytest.mark.parametrize("user,pwd", [("admin", "mal"), ("nadie", "demo1234"), ("", "x")])
def test_login_incorrecto_da_401_igual_en_todos_los_casos(user, pwd):
    r = client.post("/api/auth/login", json={"username": user, "password": pwd})
    assert r.status_code in (401, 422)
    if r.status_code == 401:
        assert r.json()["detail"] == "Usuario o contraseña incorrectos"


def test_me_con_token():
    token = login("tecnico").json()["access_token"]
    me = client.get("/api/auth/me", headers=bearer(token)).json()
    assert me["username"] == "tecnico" and me["role"] == "tecnico"
    assert "password" not in str(me)


# ---------------------------------------------------------------- tokens malos


def test_sin_token_o_token_roto_da_401():
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=bearer("basura")).status_code == 401
    assert client.get("/api/auth/me", headers={"Authorization": "Token abc"}).status_code == 401
    # el token de ejemplo de la versión anterior ya no vale
    assert client.get("/api/auth/me", headers=bearer("demo-token-admin")).status_code == 401


def test_token_caducado():
    expired = security.create_access_token(1, minutes=-1)
    assert client.get("/api/auth/me", headers=bearer(expired)).status_code == 401


def test_token_firmado_con_otra_clave_o_sin_firma():
    forged = jwt.encode({"sub": "1", "exp": time.time() + 3600}, "otra-clave-distinta-de-32-bytes!!", algorithm="HS256")
    assert client.get("/api/auth/me", headers=bearer(forged)).status_code == 401
    unsigned = jwt.encode({"sub": "1", "exp": time.time() + 3600}, None, algorithm="none")
    assert client.get("/api/auth/me", headers=bearer(unsigned)).status_code == 401


def test_token_sin_caducidad_se_rechaza():
    no_exp = jwt.encode({"sub": "1"}, security.JWT_SECRET, algorithm="HS256")
    assert client.get("/api/auth/me", headers=bearer(no_exp)).status_code == 401


def test_token_de_usuario_que_no_existe():
    assert client.get("/api/auth/me", headers=bearer(security.create_access_token(999))).status_code == 401


# ---------------------------------------------------------------- bajas y cambios de rol


class _Store(DemoUserStore):
    """Usuarios de ejemplo en los que podemos cambiar el estado durante la prueba."""


@pytest.fixture
def store():
    st = _Store()
    api.dependency_overrides[get_user_store] = lambda: st
    yield st
    api.dependency_overrides.clear()


def test_usuario_dado_de_baja_no_puede_entrar(store):
    store.get_by_username("lector").user.is_active = False
    assert login("lector").status_code == 401


def test_baja_con_token_ya_emitido_corta_el_acceso_al_instante(store):
    token = login("tecnico").json()["access_token"]
    assert client.get("/api/parcels", headers=bearer(token)).status_code == 200
    store.get_by_username("tecnico").user.is_active = False
    assert client.get("/api/parcels", headers=bearer(token)).status_code == 401


def test_cambio_de_rol_vale_con_el_token_anterior(store):
    token = login("tecnico").json()["access_token"]
    body = {"threshold_low": 5, "threshold_high": 40}
    assert client.patch("/api/sensors/t001", json=body, headers=bearer(token)).status_code == 403
    store.get_by_username("tecnico").user.role = "admin"
    assert client.patch("/api/sensors/t001", json=body, headers=bearer(token)).status_code == 200


# ---------------------------------------------------------------- permisos por rol


@pytest.mark.parametrize(
    "role,usuarios,editar_terreno",
    [("admin", 200, 201), ("tecnico", 403, 201), ("lector", 403, 403)],
)
def test_permisos_por_rol(role, usuarios, editar_terreno):
    h = bearer(login(role).json()["access_token"])
    assert client.get("/api/parcels", headers=h).status_code == 200  # todos leen
    assert client.get("/api/users", headers=h).status_code == usuarios
    zona = {"name": "Z", "type": "crop", "boundary": rectangle(36.7, -3.4, 100, 50).model_dump()}
    assert client.post("/api/parcels/1/zones", json=zona, headers=h).status_code == editar_terreno
