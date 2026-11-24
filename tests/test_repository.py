"""Pruebas del repositorio de datos (B6, issue #13). Todas contra una base de datos en memoria.

Cada prueba empieza con una base de datos NUEVA y con los mismos datos mínimos (ver ``db``), así
que ninguna depende del resultado de otra ni del fichero ``data/demeter.db``.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, select

from demeter.api import schemas as s
from demeter.db import conexion, repositorio
from demeter.models import Parcel, Sensor, SensorData, User

# Contorno de prueba: un cuadradito. Se guarda como TEXTO GeoJSON, igual que hará la API.
BOUNDARY = s.Polygon(
    coordinates=[[[-3.0, 36.0], [-3.0, 36.1], [-2.9, 36.1], [-2.9, 36.0], [-3.0, 36.0]]]
)


# Instante de referencia (UTC) para las pruebas de lecturas; ``at(5)`` es "5 minutos después".
T0 = datetime(2026, 11, 24, 8, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


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


# ---------------------------------------------------------------------------------------
# Ayudantes de las pruebas de lecturas
# ---------------------------------------------------------------------------------------


def _rows(db_engine) -> list[SensorData]:
    """Todas las filas de ``sensor_data``, leídas directamente de la tabla."""
    with Session(db_engine) as session:
        return list(session.exec(select(SensorData).order_by(SensorData.id)).all())


def _last_seen(db_engine, sensor_id: str):
    with Session(db_engine) as session:
        return session.get(Sensor, sensor_id).last_seen_at


# ---------------------------------------------------------------------------------------
# save_reading
# ---------------------------------------------------------------------------------------


def test_save_reading_guarda_y_devuelve_el_resultado_de_ingesta(db):
    result = repositorio.save_reading("t001", at(0), 21.5)
    assert isinstance(result, s.IngestResult)
    assert (result.sensor_id, result.timestamp, result.stored, result.duplicate) == (
        "t001", at(0), True, False,
    )
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].value == 21.5


def test_save_reading_repetida_no_es_error_ni_se_guarda_dos_veces(db):
    repositorio.save_reading("t001", at(0), 21.5)
    result = repositorio.save_reading("t001", at(0), 99.9)  # mismo sensor y hora, otro valor
    assert (result.stored, result.duplicate) == (False, True)
    rows = _rows(db)
    assert len(rows) == 1 and rows[0].value == 21.5  # se conserva la primera


def test_save_reading_misma_hora_en_otro_sensor_no_es_repetida(db):
    repositorio.save_reading("t001", at(0), 21.5)
    assert repositorio.save_reading("h001", at(0), 40.0).stored is True


def test_save_reading_sensor_inexistente_lanza_not_found_y_no_guarda_nada(db):
    with pytest.raises(repositorio.NotFoundError):
        repositorio.save_reading("zzz", at(0), 1.0)
    assert _rows(db) == []


def test_save_reading_acepta_sensores_desactivados(db):
    # El repositorio guarda; decidir si se rechazan los datos de un sensor de baja es regla de la API.
    assert repositorio.save_reading("a001", at(0), 50.0).stored is True


# --- fechas -------------------------------------------------------------------------------


def test_save_reading_convierte_una_fecha_con_zona_a_utc(db):
    # 10:00 en UTC+2 es el mismo instante que las 08:00 UTC.
    local = datetime(2026, 11, 24, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    result = repositorio.save_reading("t001", local, 20.0)
    assert result.timestamp == at(0) and result.timestamp.utcoffset() == timedelta(0)
    with Session(db) as session:  # el texto que hay de verdad en la tabla, sin conversiones
        stored = session.exec(text("SELECT recorded_at FROM sensor_data")).one()[0]
    assert stored.startswith("2026-11-24 08:00:00")  # guardada en UTC, no como 10:00


def test_save_reading_trata_una_fecha_sin_zona_como_utc(db):
    result = repositorio.save_reading("t001", datetime(2026, 11, 24, 8, 0), 20.0)
    assert result.timestamp == at(0)


def test_save_reading_detecta_la_repetida_aunque_llegue_en_otra_zona(db):
    repositorio.save_reading("t001", at(0), 20.0)
    local = datetime(2026, 11, 24, 10, 0, tzinfo=timezone(timedelta(hours=2)))  # = 08:00 UTC
    assert repositorio.save_reading("t001", local, 20.0).duplicate is True


# --- last_seen_at -------------------------------------------------------------------------


def test_save_reading_rellena_last_seen_at_la_primera_vez(db):
    assert _last_seen(db, "t001") is None
    repositorio.save_reading("t001", at(0), 20.0)
    assert _last_seen(db, "t001") == at(0)


def test_save_reading_last_seen_at_avanza_con_lecturas_mas_recientes(db):
    repositorio.save_reading("t001", at(0), 20.0)
    repositorio.save_reading("t001", at(5), 21.0)
    assert _last_seen(db, "t001") == at(5)


def test_save_reading_una_lectura_atrasada_se_guarda_pero_no_mueve_last_seen_at(db):
    repositorio.save_reading("t001", at(10), 20.0)
    result = repositorio.save_reading("t001", at(2), 19.0)  # llega tarde
    assert result.stored is True
    assert len(_rows(db)) == 2
    assert _last_seen(db, "t001") == at(10)  # no retrocede


def test_save_reading_repetida_tampoco_toca_last_seen_at(db):
    repositorio.save_reading("t001", at(0), 20.0)
    repositorio.save_reading("t001", at(0), 20.0)
    assert _last_seen(db, "t001") == at(0)


def test_save_reading_solo_actualiza_last_seen_at_de_su_sensor(db):
    repositorio.save_reading("t001", at(0), 20.0)
    assert _last_seen(db, "h001") is None


# ---------------------------------------------------------------------------------------
# readings
# ---------------------------------------------------------------------------------------


def _fill(sensor_id="t001", count=5):
    """``count`` lecturas, una por minuto, con valor 0, 1, 2..."""
    for i in range(count):
        repositorio.save_reading(sensor_id, at(i), float(i))


def test_readings_van_de_la_mas_antigua_a_la_mas_reciente(db):
    # Se guardan en desorden a propósito: el orden no depende de cuándo se insertaron.
    for minute in (3, 1, 2):
        repositorio.save_reading("t001", at(minute), float(minute))
    assert [r.timestamp for r in repositorio.readings("t001")] == [at(1), at(2), at(3)]


def test_readings_con_limit_se_queda_con_las_mas_recientes(db):
    _fill(count=5)
    assert [r.value for r in repositorio.readings("t001", limit=3)] == [2.0, 3.0, 4.0]


def test_readings_since_es_exclusivo(db):
    _fill(count=5)
    assert [r.value for r in repositorio.readings("t001", since=at(2))] == [3.0, 4.0]


def test_readings_since_y_limit_se_combinan(db):
    _fill(count=10)
    assert [r.value for r in repositorio.readings("t001", since=at(2), limit=2)] == [8.0, 9.0]


def test_readings_acepta_since_con_otra_zona_horaria(db):
    _fill(count=5)
    # Las 10:02 en UTC+2 son las 08:02 UTC, o sea at(2).
    since = datetime(2026, 11, 24, 10, 2, tzinfo=timezone(timedelta(hours=2)))
    assert [r.value for r in repositorio.readings("t001", since=since)] == [3.0, 4.0]


def test_readings_rellena_type_y_unit_y_devuelve_fechas_con_zona(db):
    repositorio.save_reading("t001", at(0), 21.5)
    (reading,) = repositorio.readings("t001")
    assert isinstance(reading, s.Reading)
    assert (reading.sensor_id, reading.value, reading.type, reading.unit) == (
        "t001", 21.5, "temperatura", "ºC",
    )
    assert reading.timestamp == at(0) and reading.timestamp.utcoffset() == timedelta(0)


def test_readings_no_mezcla_sensores(db):
    repositorio.save_reading("t001", at(0), 1.0)
    repositorio.save_reading("h001", at(0), 2.0)
    assert [r.value for r in repositorio.readings("h001")] == [2.0]


@pytest.mark.parametrize("sensor_id", ["zzz", "t003"])  # inexistente / sin lecturas
def test_readings_sin_resultados_devuelve_lista_vacia(db, sensor_id):
    assert repositorio.readings(sensor_id) == []


@pytest.mark.parametrize("limit", [0, -1])
def test_readings_con_limit_no_positivo_devuelve_lista_vacia(db, limit):
    _fill(count=3)
    # Ojo: en SQLite un LIMIT negativo significa "sin límite"; aquí no debe devolver todo.
    assert repositorio.readings("t001", limit=limit) == []


# ---------------------------------------------------------------------------------------
# last_reading
# ---------------------------------------------------------------------------------------


def test_last_reading_devuelve_la_mas_reciente_aunque_se_guardara_antes(db):
    repositorio.save_reading("t001", at(5), 5.0)
    repositorio.save_reading("t001", at(1), 1.0)  # guardada después, pero más antigua
    last = repositorio.last_reading("t001")
    assert isinstance(last, s.Reading) and last.value == 5.0 and last.type == "temperatura"


@pytest.mark.parametrize("sensor_id", ["zzz", "t001"])  # inexistente / sin lecturas
def test_last_reading_sin_datos_devuelve_none(db, sensor_id):
    assert repositorio.last_reading(sensor_id) is None


# ---------------------------------------------------------------------------------------
# last_readings
# ---------------------------------------------------------------------------------------


def test_last_readings_devuelve_la_ultima_de_cada_sensor_de_la_parcela(db):
    _fill("t001", count=3)  # la última vale 2.0
    repositorio.save_reading("h001", at(7), 33.0)
    result = repositorio.last_readings(1)
    assert set(result) == {"t001", "h001"}
    assert result["t001"].value == 2.0 and result["h001"].value == 33.0
    assert all(isinstance(r, s.Reading) for r in result.values())


def test_last_readings_omite_los_sensores_sin_datos(db):
    repositorio.save_reading("t001", at(0), 1.0)
    assert list(repositorio.last_readings(1)) == ["t001"]  # h001 y a001 no tienen lecturas


def test_last_readings_no_incluye_sensores_de_otras_parcelas(db):
    repositorio.save_reading("t003", at(0), 9.0)  # t003 es de la parcela 3
    assert repositorio.last_readings(1) == {}
    assert list(repositorio.last_readings(3)) == ["t003"]


def test_last_readings_incluye_sensores_desactivados_con_datos(db):
    repositorio.save_reading("a001", at(0), 50.0)  # a001 está desactivado
    assert "a001" in repositorio.last_readings(1)


@pytest.mark.parametrize("parcel_id", [2, 999])  # sin sensores / inexistente
def test_last_readings_sin_sensores_devuelve_diccionario_vacio(db, parcel_id):
    assert repositorio.last_readings(parcel_id) == {}


def test_last_readings_rellena_type_unit_y_fecha_con_zona(db):
    repositorio.save_reading("h001", at(4), 33.0)
    reading = repositorio.last_readings(1)["h001"]
    assert (reading.type, reading.unit) == ("humedad_suelo", "%")
    assert reading.timestamp == at(4) and reading.timestamp.utcoffset() == timedelta(0)


def test_last_readings_usa_una_sola_consulta(db):
    # Es lo que promete el contrato: con 3 sensores no deben hacerse 3 consultas (problema "N+1").
    _fill("t001", count=3)
    _fill("h001", count=3)
    _fill("a001", count=3)
    selects: list[str] = []

    @event.listens_for(db, "before_cursor_execute")
    def _count(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    try:
        assert len(repositorio.last_readings(1)) == 3
    finally:
        event.remove(db, "before_cursor_execute", _count)
    assert len(selects) == 1
