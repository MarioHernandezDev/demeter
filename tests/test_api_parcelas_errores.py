"""Errores del repositorio que la API traduce a un código HTTP claro, no a un 500.

Aquí se simula el error del repositorio (``AlreadyExistsError`` al reactivar una parcela cuyo nombre
ya usa otra activa del mismo propietario, ``ValueError`` con datos fuera de rango) para fijar cómo
responde la API; las pruebas del repositorio comprueban cuándo lo lanza.
"""

import pytest
from fastapi.testclient import TestClient

from demeter.api import routes
from demeter.api.app import api
from demeter.api.geo import rectangle

pytestmark = pytest.mark.usefixtures("api_db")

client = TestClient(api)


def auth(role="admin"):
    r = client.post("/api/auth/login", json={"username": role, "password": "demo1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def lanza(error):
    def _f(*_args, **_kwargs):
        raise error
    return _f


def test_reactivar_una_parcela_con_el_nombre_ocupado_da_409_y_el_mensaje(monkeypatch):
    monkeypatch.setattr(routes.repo, "set_parcel_active",
                        lanza(routes.repo.AlreadyExistsError("Ya existe una parcela activa con ese nombre")))
    r = client.patch("/api/parcels/1", json={"is_active": True}, headers=auth())
    assert r.status_code == 409 and "ese nombre" in r.json()["detail"]


def test_dar_de_baja_no_depende_del_nombre_y_sigue_funcionando():
    assert client.patch("/api/parcels/1", json={"is_active": False}, headers=auth()).status_code == 200
    assert client.patch("/api/parcels/1", json={"is_active": True}, headers=auth()).status_code == 200


def test_contorno_fuera_de_rango_en_el_repositorio_da_422(monkeypatch):
    monkeypatch.setattr(routes.repo, "set_boundary", lanza(ValueError("area_m2 fuera de rango")))
    boundary = rectangle(36.73, -3.69, 100, 50).model_dump()
    r = client.put("/api/parcels/1/boundary", json={"boundary": boundary}, headers=auth("tecnico"))
    assert r.status_code == 422 and "fuera de rango" in r.json()["detail"]


def test_un_error_inesperado_sigue_siendo_un_error_del_servidor(monkeypatch):
    # solo se traducen los errores que el repositorio promete: no se esconde cualquier fallo
    monkeypatch.setattr(routes.repo, "set_boundary", lanza(RuntimeError("fallo raro")))
    boundary = rectangle(36.73, -3.69, 100, 50).model_dump()
    with pytest.raises(RuntimeError):
        client.put("/api/parcels/1/boundary", json={"boundary": boundary}, headers=auth("tecnico"))
