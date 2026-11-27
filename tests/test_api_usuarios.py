"""Pruebas de los usuarios guardados en la base de datos: login, altas, bajas y roles.

Seed: ``admin`` (admin), ``tecnico`` y ``lector``, todos con contraseña ``demo1234``.
"""

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from demeter.api.app import api
from demeter.api.security import verify_password
from demeter.db import conexion, repositorio as repo
from demeter.models import User

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)


def login(username, password="demo1234"):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def auth(role="admin"):
    return {"Authorization": f"Bearer {login(role).json()['access_token']}"}


NUEVO = {"username": "marta", "email": "Marta@Correo.ES", "password": "una-clave-larga", "role": "lector"}


# ---------------------------------------------------------------- login desde la BD


def test_login_con_usuario_de_la_bd_y_por_correo():
    r = login("admin")
    assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
    assert r.json()["user"]["email"] and "password" not in r.text and "hash" not in r.text
    correo = r.json()["user"]["email"]
    assert login(correo).status_code == 200
    assert login(correo.upper()).status_code == 200  # el correo se busca en minúsculas


def test_contrasena_mala_usuario_inexistente_y_correo_inexistente():
    assert login("admin", "mala").status_code == 401
    assert login("nadie").status_code == 401
    assert login("nadie@correo.es").status_code == 401


def test_un_usuario_solo_de_google_no_puede_entrar_con_contrasena():
    repo.create_user("gina", "gina@correo.es", "lector", google_sub="google-123")
    assert login("gina", "demo1234").status_code == 401
    assert login("gina", "").status_code == 422
    assert login("gina@correo.es", "lo-que-sea").status_code == 401


def test_un_usuario_dado_de_baja_no_entra_y_su_token_deja_de_valer_al_instante():
    h = auth("lector")
    assert client.get("/api/auth/me", headers=h).status_code == 200
    uid = next(u["id"] for u in client.get("/api/users", headers=auth()).json() if u["username"] == "lector")
    assert client.patch(f"/api/users/{uid}", json={"is_active": False}, headers=auth()).status_code == 200
    assert client.get("/api/auth/me", headers=h).status_code == 401  # mismo token, ya no vale
    assert login("lector").status_code == 401
    client.patch(f"/api/users/{uid}", json={"is_active": True}, headers=auth())
    assert login("lector").status_code == 200  # reactivado


def test_un_cambio_de_rol_vale_al_instante():
    h = auth("tecnico")
    assert client.get("/api/users", headers=h).status_code == 403
    uid = next(u["id"] for u in client.get("/api/users", headers=auth()).json() if u["username"] == "tecnico")
    client.patch(f"/api/users/{uid}", json={"role": "admin"}, headers=auth())
    assert client.get("/api/users", headers=h).status_code == 200  # el mismo token, con rol nuevo


# ---------------------------------------------------------------- alta


def test_crear_usuario_guarda_el_hash_y_puede_entrar():
    r = client.post("/api/users", json=NUEVO, headers=auth())
    assert r.status_code == 201
    u = r.json()
    assert u["username"] == "marta" and u["email"] == "marta@correo.es" and u["role"] == "lector"
    assert u["email_verified"] is False and "password" not in u
    with Session(conexion.get_engine()) as s:
        row = s.exec(select(User).where(User.username == "marta")).one()
    assert row.password_hash != NUEVO["password"] and verify_password(NUEVO["password"], row.password_hash)
    assert login("marta", NUEVO["password"]).status_code == 200
    assert login("marta@correo.es", NUEVO["password"]).status_code == 200


def test_crear_usuario_repetido_409_en_nombre_y_en_correo_sin_mirar_mayusculas():
    client.post("/api/users", json=NUEVO, headers=auth())
    assert client.post("/api/users", json={**NUEVO, "email": "otra@correo.es"}, headers=auth()).status_code == 409
    assert client.post("/api/users", json={**NUEVO, "username": "otra"}, headers=auth()).status_code == 409
    assert client.post("/api/users", json={**NUEVO, "username": "otra", "email": "MARTA@correo.es"},
                       headers=auth()).status_code == 409
    assert len(client.get("/api/users", headers=auth()).json()) == 4


@pytest.mark.parametrize("cambio", [
    {"username": "con@arroba"}, {"username": "con espacio"}, {"username": ""},
    {"email": "sin-arroba"}, {"email": "a@b"}, {"email": "con espacio@x.es"},
    {"password": "corta"}, {"password": "x" * 73}, {"role": "dios"},
])
def test_crear_usuario_con_datos_malos_422(cambio):
    assert client.post("/api/users", json={**NUEVO, **cambio}, headers=auth()).status_code == 422
    assert len(client.get("/api/users", headers=auth()).json()) == 3


def test_el_hash_nunca_sale_en_el_listado():
    texto = client.get("/api/users", headers=auth()).text
    assert "$2b$" not in texto and "password" not in texto


# ---------------------------------------------------------------- cambios y protecciones


def uid(nombre):
    return next(u["id"] for u in client.get("/api/users", headers=auth()).json() if u["username"] == nombre)


def test_un_admin_no_puede_quitarse_el_rol_ni_darse_de_baja():
    me = uid("admin")
    assert client.patch(f"/api/users/{me}", json={"role": "lector"}, headers=auth()).status_code == 409
    assert client.patch(f"/api/users/{me}", json={"is_active": False}, headers=auth()).status_code == 409
    assert login("admin").json()["user"]["role"] == "admin"


def test_un_admin_puede_dar_de_baja_a_otro_admin():
    client.patch(f"/api/users/{uid('tecnico')}", json={"role": "admin"}, headers=auth())
    assert client.patch(f"/api/users/{uid('tecnico')}", json={"is_active": False}, headers=auth()).status_code == 200
    assert login("tecnico").status_code == 401 and login("admin").status_code == 200


def test_actualizar_usuario_casos_raros():
    h = auth()
    assert client.patch("/api/users/9999", json={"role": "lector"}, headers=h).status_code == 404
    assert client.patch(f"/api/users/{uid('lector')}", json={"role": None}, headers=h).status_code == 422
    assert client.patch(f"/api/users/{uid('lector')}", json={"is_active": None}, headers=h).status_code == 422
    assert client.patch(f"/api/users/{uid('lector')}", json={"role": "dios"}, headers=h).status_code == 422
    # un cuerpo vacío no cambia nada
    antes = client.get("/api/users", headers=h).json()
    assert client.patch(f"/api/users/{uid('lector')}", json={}, headers=h).status_code == 200
    assert client.get("/api/users", headers=h).json() == antes


def test_solo_el_admin_gestiona_usuarios():
    for role in ("tecnico", "lector"):
        h = auth(role)
        assert client.get("/api/users", headers=h).status_code == 403
        assert client.post("/api/users", json=NUEVO, headers=h).status_code == 403
        assert client.patch("/api/users/1", json={"role": "lector"}, headers=h).status_code == 403
