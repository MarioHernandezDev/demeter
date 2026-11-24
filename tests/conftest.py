"""Fixtures compartidas por las pruebas de la API."""

import bcrypt
import pytest
from sqlalchemy import insert, update
from sqlmodel import Session, SQLModel

from demeter.api import sample_data as d
from demeter.api import schemas as s
from demeter.db import conexion, repositorio as repo, seed
from demeter.models import Sensor, SensorData
from demeter.services import weather


# bcrypt es lento a propósito: en las pruebas se usa el mínimo de rondas (4) y el hash de
# «demo1234» se calcula una sola vez para los 3 usuarios. Es un hash bcrypt de verdad.
_DEMO_HASH = bcrypt.hashpw(b"demo1234", bcrypt.gensalt(rounds=4)).decode("ascii")


@pytest.fixture
def api_db(monkeypatch):
    """Base de datos en memoria, nueva en cada prueba y con los datos del seed (#14).

    Las pruebas de la API que tocan parcelas y sensores usan esto en vez del fichero
    ``data/demeter.db``: así no dependen de él ni se estropean entre sí.
    """
    engine = conexion.make_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(conexion, "_engine", engine)
    # El seed calcularía el hash 3 veces por prueba: se le da el ya calculado.
    monkeypatch.setattr(seed, "hash_password", lambda _password: _DEMO_HASH)
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


@pytest.fixture
def datos_ejemplo(api_db):
    """``api_db`` más los datos de ejemplo de ``sample_data`` metidos en la base de datos: contorno,
    zonas y elementos de las fincas 1 y 2, los movimientos de la 1 y 24 h de lecturas (una por
    minuto) de todos los sensores. Para las pruebas que necesitan una finca «con vida»."""
    for pid, parcel in d.PARCELS.items():
        repo.set_boundary(pid, parcel.boundary, parcel.area_m2)
    for zone in d.ZONES:
        repo.create_zone(zone.parcel_id, s.ZoneCreate(
            name=zone.name, type=zone.type, crop=zone.crop, boundary=zone.boundary), zone.area_m2)
    for element in d.ELEMENTS:
        repo.create_element(element.parcel_id, s.ElementCreate(
            type=element.type, subtype=element.subtype, geometry=element.geometry,
            height_m=element.height_m))
    for tx in d.transactions(1):
        repo.create_transaction(1, s.TransactionCreate(
            kind=tx.kind, category=tx.category, amount=tx.amount, occurred_on=tx.occurred_on,
            description=tx.description))
    with conexion.open_session() as session:
        for sensor in d.SENSORS:
            series = d.readings(sensor)
            session.execute(insert(SensorData), [
                {"sensor_id": sensor.id, "recorded_at": r.timestamp, "value": r.value} for r in series])
            session.execute(update(Sensor).where(Sensor.id == sensor.id).values(
                last_seen_at=series[-1].timestamp))
        session.commit()
    return api_db
