"""Fixtures compartidas por las pruebas de la API."""

import pytest
from sqlmodel import Session, SQLModel

from demeter.db import conexion, seed
from demeter.services import weather


@pytest.fixture
def api_db(monkeypatch):
    """Base de datos en memoria, nueva en cada prueba y con los datos del seed (#14).

    Las pruebas de la API que tocan parcelas y sensores usan esto en vez del fichero
    ``data/demeter.db``: así no dependen de él ni se estropean entre sí.
    """
    engine = conexion.make_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(conexion, "_engine", engine)
    # bcrypt es lento a propósito y el seed lo llamaría 3 veces por prueba: aquí no importa.
    monkeypatch.setattr(seed, "hash_password", lambda _password: "x")
    with Session(engine) as session:
        seed.seed(session)
        session.commit()
    return engine


@pytest.fixture(autouse=True)
def sin_internet(monkeypatch):
    """Ninguna prueba llama a Open-Meteo de verdad: el clima falla salvo que la prueba lo ponga."""

    def sin_red(latitude, longitude):
        raise OSError("sin internet (prueba)")

    monkeypatch.setattr(weather, "_fetch_json", sin_red)
    weather.clear_cache()
    yield
    weather.clear_cache()
