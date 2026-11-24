"""Pruebas del seed (B3, issue #14) contra una base de datos en memoria."""

import pytest
from sqlmodel import Session, SQLModel, select

from demeter.db import conexion, seed
from demeter.models import Parcel, Sensor, Tank, User


@pytest.fixture
def engine(monkeypatch):
    engine = conexion.make_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(conexion, "_engine", engine)
    # bcrypt es lento a propósito; en las pruebas da igual la huella.
    monkeypatch.setattr(seed, "hash_password", lambda _password: "x")
    return engine


def _run(engine) -> dict[str, int]:
    with Session(engine) as session:
        created = seed.seed(session)
        session.commit()
    return created


def test_seed_crea_todo_la_primera_vez(engine):
    assert _run(engine) == {"users": 3, "parcels": 3, "sensors": 14, "tanks": 3}


def test_seed_se_puede_repetir_sin_duplicar(engine):
    _run(engine)
    assert _run(engine) == {"users": 0, "parcels": 0, "sensors": 0, "tanks": 0}
    with Session(engine) as session:
        assert len(session.exec(select(Tank)).all()) == 3


def test_seed_cada_deposito_esta_en_su_finca_y_enlazado_a_su_sensor_de_nivel(engine):
    _run(engine)
    with Session(engine) as session:
        for tank in session.exec(select(Tank)).all():
            sensor = session.get(Sensor, tank.level_sensor_id)
            assert sensor.type == "nivel_deposito"
            assert sensor.parcel_id == tank.parcel_id  # el sensor es de la misma finca


def test_seed_un_deposito_por_finca(engine):
    _run(engine)
    with Session(engine) as session:
        for parcel in session.exec(select(Parcel)).all():
            assert len(session.exec(select(Tank).where(Tank.parcel_id == parcel.id)).all()) == 1


def test_seed_completa_lo_que_falta_en_una_base_de_datos_antigua(engine):
    # Una base de datos sembrada antes de que existieran los depósitos: el seed solo añade estos.
    _run(engine)
    with Session(engine) as session:
        for tank in session.exec(select(Tank)).all():
            session.delete(tank)
        session.commit()
    assert _run(engine) == {"users": 0, "parcels": 0, "sensors": 0, "tanks": 3}


def test_seed_usuarios_verificados(engine):
    _run(engine)
    with Session(engine) as session:
        assert all(u.email_verified for u in session.exec(select(User)).all())
