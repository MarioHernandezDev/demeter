"""Pruebas del repositorio de datos (B6, issue #13). Todas contra una base de datos en memoria.

Cada prueba empieza con una base de datos NUEVA y con los mismos datos mínimos (ver ``db``), así
que ninguna depende del resultado de otra ni del fichero ``data/demeter.db``.
"""

import pytest
from sqlmodel import Session, SQLModel

from demeter.api import schemas as s
from demeter.db import conexion, repositorio
from demeter.models import Parcel, Sensor, User

# Contorno de prueba: un cuadradito. Se guarda como TEXTO GeoJSON, igual que hará la API.
BOUNDARY = s.Polygon(
    coordinates=[[[-3.0, 36.0], [-3.0, 36.1], [-2.9, 36.1], [-2.9, 36.0], [-3.0, 36.0]]]
)


@pytest.fixture
def db(monkeypatch):
    """Base de datos en memoria con: 1 usuario, 3 parcelas y 4 sensores.

    - Parcela 1 «Activa»: con contorno y 3 sensores (uno de ellos desactivado).
    - Parcela 2 «Sin contorno»: activa, sin contorno y sin sensores.
    - Parcela 3 «De baja»: desactivada, con 1 sensor.
    """
    engine = conexion.make_engine("sqlite://")  # en memoria, con claves foráneas activas
    SQLModel.metadata.create_all(engine)
    # El repositorio pide su motor a ``conexion``; se le da el de la prueba.
    monkeypatch.setattr(conexion, "_engine", engine)

    with Session(engine) as session:
        session.add(User(username="admin", email="a@x.es", password_hash="x", role="admin"))
        session.flush()
        for name, active, boundary in [
            ("Activa", True, BOUNDARY.model_dump_json()),
            ("Sin contorno", True, None),
            ("De baja", False, None),
        ]:
            session.add(
                Parcel(
                    owner_id=1, name=name, location="Motril", crop="aguacate",
                    latitude=36.0, longitude=-3.0, boundary=boundary, is_active=active,
                    area_m2=1234.5 if boundary else None,
                )
            )
        session.flush()
        for code, parcel_id, kind, unit, active in [
            ("t001", 1, "temperatura", "ºC", True),
            ("h001", 1, "humedad_suelo", "%", True),
            ("a001", 1, "humedad_ambiente", "%", False),
            ("t003", 3, "temperatura", "ºC", True),
        ]:
            session.add(
                Sensor(
                    id=code, parcel_id=parcel_id, type=kind, unit=unit, description="x",
                    threshold_low=8, threshold_high=None, is_active=active,
                )
            )
        session.commit()
    yield engine


# ---------------------------------------------------------------------------------------
# get_sensor
# ---------------------------------------------------------------------------------------


def test_get_sensor_devuelve_el_esquema_de_la_api(db):
    sensor = repositorio.get_sensor("t001")
    assert isinstance(sensor, s.Sensor)
    assert (sensor.id, sensor.parcel_id, sensor.type, sensor.unit) == ("t001", 1, "temperatura", "ºC")
    # Un umbral con valor y otro vacío: el vacío debe llegar como None, no como 0.
    assert sensor.threshold_low == 8 and sensor.threshold_high is None


def test_get_sensor_inexistente_devuelve_none(db):
    assert repositorio.get_sensor("zzz") is None


def test_get_sensor_devuelve_tambien_los_desactivados(db):
    assert repositorio.get_sensor("a001").is_active is False


# ---------------------------------------------------------------------------------------
# parcel_sensors
# ---------------------------------------------------------------------------------------


def test_parcel_sensors_incluye_desactivados_y_va_ordenado_por_codigo(db):
    sensors = repositorio.parcel_sensors(1)
    assert [x.id for x in sensors] == ["a001", "h001", "t001"]
    assert [x.is_active for x in sensors] == [False, True, True]


def test_parcel_sensors_solo_trae_los_de_esa_parcela(db):
    assert [x.id for x in repositorio.parcel_sensors(3)] == ["t003"]


@pytest.mark.parametrize("parcel_id", [2, 999])  # sin sensores / inexistente
def test_parcel_sensors_sin_resultados_devuelve_lista_vacia(db, parcel_id):
    assert repositorio.parcel_sensors(parcel_id) == []


# ---------------------------------------------------------------------------------------
# list_parcels
# ---------------------------------------------------------------------------------------


def test_list_parcels_oculta_las_de_baja_por_defecto(db):
    parcels = repositorio.list_parcels()
    assert [p.name for p in parcels] == ["Activa", "Sin contorno"]
    assert all(isinstance(p, s.Parcel) for p in parcels)


def test_list_parcels_con_include_inactive_las_devuelve_todas_por_orden(db):
    assert [p.id for p in repositorio.list_parcels(include_inactive=True)] == [1, 2, 3]


def test_list_parcels_sin_parcelas_devuelve_lista_vacia(monkeypatch):
    engine = conexion.make_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(conexion, "_engine", engine)
    assert repositorio.list_parcels() == []


# ---------------------------------------------------------------------------------------
# get_parcel
# ---------------------------------------------------------------------------------------


def test_get_parcel_convierte_el_texto_geojson_en_polygon(db):
    parcel = repositorio.get_parcel(1)
    assert isinstance(parcel, s.ParcelDetail)
    assert isinstance(parcel.boundary, s.Polygon)
    assert parcel.boundary == BOUNDARY
    assert parcel.area_m2 == 1234.5


def test_get_parcel_sin_contorno_devuelve_boundary_none(db):
    parcel = repositorio.get_parcel(2)
    assert parcel.boundary is None and parcel.area_m2 is None


def test_get_parcel_devuelve_tambien_las_de_baja(db):
    # A diferencia de list_parcels, pedir UNA parcela por su id no la oculta.
    assert repositorio.get_parcel(3).name == "De baja"


def test_get_parcel_inexistente_devuelve_none(db):
    assert repositorio.get_parcel(999) is None


# ---------------------------------------------------------------------------------------
# Reglas generales
# ---------------------------------------------------------------------------------------


def test_lo_devuelto_sigue_siendo_valido_con_la_sesion_cerrada(db):
    """Regla 1 del contrato: no se devuelven filas ligadas a una sesión, sino esquemas."""
    parcel = repositorio.get_parcel(1)
    sensors = repositorio.parcel_sensors(1)
    # Si fueran filas de la base de datos, leer sus campos ahora fallaría (sesión cerrada).
    assert parcel.name == "Activa" and sensors[0].parcel_id == 1


def test_los_errores_se_importan_del_repositorio():
    # Los usará la pieza C (y las siguientes entregas); el contrato dice que se importan de aquí.
    assert issubclass(repositorio.NotFoundError, Exception)
    assert issubclass(repositorio.AlreadyExistsError, Exception)
