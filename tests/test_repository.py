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
from demeter.models import Alert, Parcel, Sensor, SensorData, Tank, TerrainElement, User, Zone

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
# update_sensor
# ---------------------------------------------------------------------------------------


def test_update_sensor_cambia_solo_los_campos_indicados(db):
    result = repositorio.update_sensor("t001", {"threshold_high": 40.0})
    assert isinstance(result, s.Sensor)
    assert result.threshold_high == 40.0
    assert result.threshold_low == 8  # el que no venía en ``changes`` se queda como estaba
    assert repositorio.get_sensor("t001").threshold_high == 40.0  # y queda guardado


def test_update_sensor_un_none_explicito_deja_el_campo_vacio(db):
    # t001 tiene threshold_low=8: "ponlo a None" (quitar el umbral) no es lo mismo que "no lo toques".
    assert repositorio.update_sensor("t001", {"threshold_low": None}).threshold_low is None


def test_update_sensor_cambia_la_posicion(db):
    result = repositorio.update_sensor("t001", {"latitude": 36.7, "longitude": -3.5})
    assert (result.latitude, result.longitude) == (36.7, -3.5)


def test_update_sensor_puede_desactivar_y_reactivar(db):
    assert repositorio.update_sensor("t001", {"is_active": False}).is_active is False
    assert repositorio.update_sensor("t001", {"is_active": True}).is_active is True


def test_update_sensor_sin_cambios_devuelve_el_sensor_igual(db):
    assert repositorio.update_sensor("t001", {}) == repositorio.get_sensor("t001")


def test_update_sensor_inexistente_devuelve_none(db):
    assert repositorio.update_sensor("zzz", {"threshold_low": 1.0}) is None


@pytest.mark.parametrize("field", ["id", "parcel_id", "type", "unit", "description", "last_seen_at", "otra"])
def test_update_sensor_rechaza_campos_no_editables(db, field):
    with pytest.raises(ValueError):
        repositorio.update_sensor("t001", {field: "x"})


def test_update_sensor_si_hay_un_campo_invalido_no_cambia_nada(db):
    with pytest.raises(ValueError):
        repositorio.update_sensor("t001", {"threshold_high": 99.0, "type": "luminosidad"})
    sensor = repositorio.get_sensor("t001")
    assert sensor.threshold_high is None and sensor.type == "temperatura"  # ni siquiera el válido


def test_update_sensor_is_active_no_admite_none(db):
    with pytest.raises(ValueError):
        repositorio.update_sensor("t001", {"is_active": None})
    assert repositorio.get_sensor("t001").is_active is True


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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_save_reading_rechaza_valores_no_finitos_y_no_guarda_nada(db, value):
    with pytest.raises(ValueError):
        repositorio.save_reading("t001", at(0), value)
    assert _rows(db) == []
    assert _last_seen(db, "t001") is None  # tampoco mueve last_seen_at


def test_save_reading_acepta_cero_y_negativos(db):
    # Cero y bajo cero son lecturas normales (una helada), no valores inválidos.
    assert repositorio.save_reading("t001", at(0), 0.0).stored is True
    assert repositorio.save_reading("t001", at(1), -3.5).stored is True


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


# ---------------------------------------------------------------------------------------
# set_boundary
# ---------------------------------------------------------------------------------------

NEW_BOUNDARY = s.Polygon(
    coordinates=[[[-4.0, 37.0], [-4.0, 37.1], [-3.9, 37.1], [-3.9, 37.0], [-4.0, 37.0]]]
)


def test_set_boundary_guarda_contorno_y_superficie_y_devuelve_la_parcela(db):
    result = repositorio.set_boundary(2, NEW_BOUNDARY, 5000.0)  # la parcela 2 no tenía contorno
    assert isinstance(result, s.ParcelDetail)
    assert result.boundary == NEW_BOUNDARY and result.area_m2 == 5000.0
    # Y queda guardado: una lectura posterior lo ve.
    assert repositorio.get_parcel(2).boundary == NEW_BOUNDARY


def test_set_boundary_se_guarda_como_texto_geojson(db):
    repositorio.set_boundary(2, NEW_BOUNDARY, 5000.0)
    with Session(db) as session:
        text_in_db = session.get(Parcel, 2).boundary
    assert isinstance(text_in_db, str) and s.Polygon.model_validate_json(text_in_db) == NEW_BOUNDARY


def test_set_boundary_sustituye_el_contorno_anterior(db):
    assert repositorio.get_parcel(1).boundary == BOUNDARY
    repositorio.set_boundary(1, NEW_BOUNDARY, 77.0)
    parcel = repositorio.get_parcel(1)
    assert parcel.boundary == NEW_BOUNDARY and parcel.area_m2 == 77.0


def test_set_boundary_no_toca_el_resto_de_la_parcela_ni_otras_parcelas(db):
    repositorio.set_boundary(1, NEW_BOUNDARY, 77.0)
    parcel = repositorio.get_parcel(1)
    assert (parcel.name, parcel.location, parcel.crop) == ("Activa", "Motril", "aguacate")
    assert repositorio.get_parcel(2).boundary is None  # la otra parcela sigue igual


def test_set_boundary_parcela_inexistente_devuelve_none(db):
    assert repositorio.set_boundary(999, NEW_BOUNDARY, 1.0) is None


def test_set_boundary_acepta_parcelas_de_baja(db):
    # El repositorio guarda; decidir si se puede editar una parcela de baja es regla de la API.
    assert repositorio.set_boundary(3, NEW_BOUNDARY, 1.0).boundary == NEW_BOUNDARY


# ---------------------------------------------------------------------------------------
# set_parcel_active
# ---------------------------------------------------------------------------------------


def _active_sensors(parcel_id: int) -> dict[str, bool]:
    return {x.id: x.is_active for x in repositorio.parcel_sensors(parcel_id)}


def test_set_parcel_active_false_da_de_baja_la_parcela_y_todos_sus_sensores(db):
    assert _active_sensors(1) == {"a001": False, "h001": True, "t001": True}
    result = repositorio.set_parcel_active(1, False)
    assert isinstance(result, s.Parcel) and result.id == 1
    assert [p.id for p in repositorio.list_parcels()] == [2]  # ya no sale entre las activas
    assert _active_sensors(1) == {"a001": False, "h001": False, "t001": False}


def test_set_parcel_active_no_toca_los_sensores_de_otras_parcelas(db):
    repositorio.set_parcel_active(1, False)
    assert _active_sensors(3) == {"t003": True}


def test_set_parcel_active_true_reactiva_la_parcela_y_todos_sus_sensores(db):
    repositorio.set_parcel_active(3, True)
    assert [p.id for p in repositorio.list_parcels()] == [1, 2, 3]
    assert _active_sensors(3) == {"t003": True}


def test_set_parcel_active_reactivar_reactiva_tambien_los_sensores_desactivados_antes(db):
    # Contrato: reactivar la parcela reactiva TODOS sus sensores. a001 estaba desactivado por
    # separado desde el principio, y tras dar de baja y reactivar la parcela vuelve a estar activo.
    repositorio.set_parcel_active(1, False)
    repositorio.set_parcel_active(1, True)
    assert _active_sensors(1) == {"a001": True, "h001": True, "t001": True}


def test_set_parcel_active_repetir_la_misma_orden_no_cambia_nada(db):
    repositorio.set_parcel_active(1, False)
    repositorio.set_parcel_active(1, False)
    assert _active_sensors(1) == {"a001": False, "h001": False, "t001": False}


def test_set_parcel_active_parcela_inexistente_devuelve_none(db):
    assert repositorio.set_parcel_active(999, False) is None


def test_set_parcel_active_dar_de_baja_conserva_las_lecturas(db):
    # Decisión del proyecto: dar de baja = desactivar, no borrar. El historial se conserva.
    repositorio.save_reading("t001", at(0), 20.0)
    repositorio.set_parcel_active(1, False)
    assert [r.value for r in repositorio.readings("t001")] == [20.0]


def test_set_parcel_active_es_una_sola_transaccion(db):
    """Si falla al desactivar los sensores, la parcela tampoco debe quedar de baja."""

    @event.listens_for(db, "before_cursor_execute")
    def _fail_on_sensors(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE SENSORS"):
            raise RuntimeError("fallo simulado")

    try:
        with pytest.raises(Exception, match="fallo simulado"):
            repositorio.set_parcel_active(1, False)
    finally:
        event.remove(db, "before_cursor_execute", _fail_on_sensors)

    assert 1 in [p.id for p in repositorio.list_parcels()]  # la parcela sigue activa
    assert _active_sensors(1) == {"a001": False, "h001": True, "t001": True}  # sin cambios


# ---------------------------------------------------------------------------------------
# save_reading con la sesión de quien llama (ingesta + motor de alertas en una transacción)
# ---------------------------------------------------------------------------------------


def test_save_reading_con_session_no_confirma(db):
    with Session(db) as session:
        result = repositorio.save_reading("t001", at(0), 20.0, session=session)
        assert result.stored is True
        session.rollback()  # quien llama decide deshacer
    assert _rows(db) == []  # no quedó nada: la función no hizo commit por su cuenta
    assert _last_seen(db, "t001") is None


def test_save_reading_con_session_se_guarda_al_confirmar_quien_llama(db):
    with Session(db) as session:
        repositorio.save_reading("t001", at(0), 20.0, session=session)
        session.commit()
    assert len(_rows(db)) == 1
    assert _last_seen(db, "t001") == at(0)


def test_save_reading_con_session_actualiza_last_seen_at_dentro_de_la_sesion(db):
    # El motor de alertas lee el sensor en la MISMA sesión: debe ver ya el last_seen_at nuevo.
    with Session(db) as session:
        # El sensor ya está cargado en la sesión antes de guardar (p. ej. la API lo leyó para
        # validarlo). Se guarda en una variable a propósito: SQLAlchemy solo recuerda los objetos
        # que siguen en uso, y sin la variable lo volvería a leer de la base de datos y el test no
        # comprobaría nada.
        sensor = session.get(Sensor, "t001")
        repositorio.save_reading("t001", at(3), 20.0, session=session)
        assert sensor.last_seen_at == at(3)
        session.rollback()


def test_save_reading_con_session_repetida_no_estropea_la_transaccion(db):
    with Session(db) as session:
        repositorio.save_reading("t001", at(0), 20.0, session=session)
        assert repositorio.save_reading("t001", at(0), 20.0, session=session).duplicate is True
        repositorio.save_reading("t001", at(1), 21.0, session=session)  # la sesión sigue usable
        session.commit()
    assert len(_rows(db)) == 2


def test_save_reading_con_session_y_motor_de_alertas_en_una_sola_transaccion(db):
    """Lo que hará la ingesta: guardar, evaluar y un único commit (contrato de alertas, 8.9)."""
    from demeter.services.alerts import evaluar_lectura

    with Session(db) as session:
        repositorio.save_reading("t001", at(0), 2.0, session=session)  # umbral bajo de t001 = 8
        abiertas = evaluar_lectura(session, "t001", at(0), 2.0)
        assert [a.type for a in abiertas] == ["LOW"]
        session.commit()
    assert len(_rows(db)) == 1
    page, total = repositorio.list_alerts(sensor_id="t001")
    assert total == 1 and page[0].type == "LOW" and page[0].value == 2.0


def test_save_reading_con_session_y_motor_si_falla_no_se_guarda_ni_la_lectura(db):
    from demeter.services.alerts import evaluar_lectura

    with Session(db) as session:
        repositorio.save_reading("t001", at(0), 2.0, session=session)
        evaluar_lectura(session, "t001", at(0), 2.0)
        session.rollback()  # p. ej. falló algo después
    assert _rows(db) == []
    assert repositorio.list_alerts() == ([], 0)


# ---------------------------------------------------------------------------------------
# Alertas: datos de prueba
# ---------------------------------------------------------------------------------------


def _add_alert(db_engine, sensor_id, kind, minute, resolved=None, ack=False, value=None):
    with Session(db_engine) as session:
        row = Alert(
            sensor_id=sensor_id, type=kind, opened_at=at(minute), message=f"{kind} {sensor_id}",
            resolved_at=at(resolved) if resolved is not None else None,
            acknowledged=ack, value=value, threshold=8.0 if value is not None else None,
        )
        session.add(row)
        session.commit()
        return row.id


@pytest.fixture
def alerts(db):
    """Cinco alertas: cuatro en la parcela 1 y una en la 3. Devuelve sus ids por nombre."""
    return {
        "t001_low_resuelta": _add_alert(db, "t001", "LOW", 1, resolved=5, ack=True, value=2.0),
        "h001_high_activa": _add_alert(db, "h001", "HIGH", 2, value=70.0),
        "t001_offline_activa": _add_alert(db, "t001", "OFFLINE", 3),
        "a001_low_activa": _add_alert(db, "a001", "LOW", 4, value=1.0),
        "t003_offline_activa": _add_alert(db, "t003", "OFFLINE", 6),
    }


# ---------------------------------------------------------------------------------------
# list_alerts
# ---------------------------------------------------------------------------------------


def test_list_alerts_devuelve_todas_las_mas_recientes_primero_y_el_total(db, alerts):
    page, total = repositorio.list_alerts()
    assert total == 5
    assert [a.timestamp for a in page] == [at(6), at(4), at(3), at(2), at(1)]
    assert all(isinstance(a, s.Alert) for a in page)


def test_list_alerts_traduce_opened_at_a_timestamp_y_rellena_los_campos(db, alerts):
    page, _ = repositorio.list_alerts(alert_type="LOW", active=False)
    (alert,) = page
    assert alert.id == alerts["t001_low_resuelta"]
    assert (alert.sensor_id, alert.type, alert.value, alert.threshold) == ("t001", "LOW", 2.0, 8.0)
    assert alert.timestamp == at(1) and alert.timestamp.utcoffset() == timedelta(0)
    assert alert.resolved_at == at(5) and alert.acknowledged is True


def test_list_alerts_filtra_por_parcela(db, alerts):
    page, total = repositorio.list_alerts(parcel_id=3)
    assert total == 1 and [a.sensor_id for a in page] == ["t003"]
    assert repositorio.list_alerts(parcel_id=1)[1] == 4


def test_list_alerts_filtra_no_leidas(db, alerts):
    page, total = repositorio.list_alerts(unread_only=True)
    assert total == 4 and alerts["t001_low_resuelta"] not in [a.id for a in page]


def test_list_alerts_filtra_por_tipo_y_por_sensor(db, alerts):
    assert repositorio.list_alerts(alert_type="OFFLINE")[1] == 2
    assert [a.type for a in repositorio.list_alerts(sensor_id="t001")[0]] == ["OFFLINE", "LOW"]


def test_list_alerts_filtra_activas_y_resueltas(db, alerts):
    activas, n_activas = repositorio.list_alerts(active=True)
    assert n_activas == 4 and all(a.resolved_at is None for a in activas)
    resueltas, n_resueltas = repositorio.list_alerts(active=False)
    assert n_resueltas == 1 and resueltas[0].resolved_at is not None


def test_list_alerts_combina_filtros(db, alerts):
    page, total = repositorio.list_alerts(parcel_id=1, active=True, alert_type="LOW")
    assert total == 1 and page[0].sensor_id == "a001"


def test_list_alerts_pagina_y_el_total_no_depende_de_la_pagina(db, alerts):
    first, total1 = repositorio.list_alerts(limit=2)
    second, total2 = repositorio.list_alerts(limit=2, offset=2)
    third, _ = repositorio.list_alerts(limit=2, offset=4)
    assert total1 == total2 == 5
    ids = [a.id for a in first + second + third]
    assert len(ids) == 5 and len(set(ids)) == 5  # ni repetidas ni saltadas


def test_list_alerts_pagina_estable_con_misma_hora(db):
    # Dos alertas abiertas en el mismo instante: el id desempata y el orden no cambia.
    first = _add_alert(db, "t001", "LOW", 0, value=1.0)
    second = _add_alert(db, "h001", "LOW", 0, value=1.0)
    assert [a.id for a in repositorio.list_alerts()[0]] == [second, first]


def test_list_alerts_por_defecto_trae_20(db):
    for minute in range(25):
        _add_alert(db, "t001", "LOW", minute, resolved=minute, value=1.0)
    page, total = repositorio.list_alerts()
    assert len(page) == 20 and total == 25


@pytest.mark.parametrize("limit", [0, -1])
def test_list_alerts_limit_no_positivo_da_pagina_vacia_pero_total_real(db, alerts, limit):
    assert repositorio.list_alerts(limit=limit) == ([], 5)


def test_list_alerts_offset_negativo_lanza_value_error(db, alerts):
    with pytest.raises(ValueError):
        repositorio.list_alerts(offset=-1)


def test_list_alerts_sin_alertas(db):
    assert repositorio.list_alerts() == ([], 0)
    assert repositorio.list_alerts(parcel_id=999) == ([], 0)


# ---------------------------------------------------------------------------------------
# set_acknowledged
# ---------------------------------------------------------------------------------------


def test_set_acknowledged_marca_y_desmarca(db, alerts):
    alert_id = alerts["h001_high_activa"]
    assert repositorio.set_acknowledged(alert_id, True).acknowledged is True
    assert alert_id not in [a.id for a in repositorio.list_alerts(unread_only=True)[0]]
    assert repositorio.set_acknowledged(alert_id, False).acknowledged is False


def test_set_acknowledged_no_resuelve_la_alerta(db, alerts):
    # Leída y resuelta son dos cosas distintas: leerla no la cierra.
    assert repositorio.set_acknowledged(alerts["h001_high_activa"], True).resolved_at is None


def test_set_acknowledged_inexistente_devuelve_none(db, alerts):
    assert repositorio.set_acknowledged(999, True) is None


# ---------------------------------------------------------------------------------------
# acknowledge_all
# ---------------------------------------------------------------------------------------


def test_acknowledge_all_marca_las_de_la_parcela_y_devuelve_cuantas(db, alerts):
    # Parcela 1: 4 alertas, 1 ya leída -> marca 3.
    assert repositorio.acknowledge_all(1) == 3
    assert repositorio.list_alerts(parcel_id=1, unread_only=True) == ([], 0)


def test_acknowledge_all_no_toca_otras_parcelas(db, alerts):
    repositorio.acknowledge_all(1)
    assert repositorio.list_alerts(parcel_id=3, unread_only=True)[1] == 1


def test_acknowledge_all_repetida_devuelve_cero(db, alerts):
    repositorio.acknowledge_all(1)
    assert repositorio.acknowledge_all(1) == 0


def test_acknowledge_all_no_resuelve_las_alertas(db, alerts):
    repositorio.acknowledge_all(1)
    assert repositorio.list_alerts(parcel_id=1, active=True)[1] == 3


@pytest.mark.parametrize("parcel_id", [2, 999])  # sin alertas / inexistente
def test_acknowledge_all_sin_alertas_devuelve_cero(db, alerts, parcel_id):
    assert repositorio.acknowledge_all(parcel_id) == 0


# ---------------------------------------------------------------------------------------
# sensors_last_seen
# ---------------------------------------------------------------------------------------


def test_sensors_last_seen_solo_activos_de_parcelas_activas(db):
    # a001 está desactivado y t003 está en una parcela de baja: no salen.
    assert repositorio.sensors_last_seen() == [("h001", None), ("t001", None)]


def test_sensors_last_seen_devuelve_la_hora_con_zona(db):
    repositorio.save_reading("t001", at(7), 20.0)
    result = dict(repositorio.sensors_last_seen())
    assert result["t001"] == at(7) and result["t001"].utcoffset() == timedelta(0)
    assert result["h001"] is None  # nunca ha enviado datos: "esperando", no caído


def test_sensors_last_seen_sigue_a_las_bajas_y_reactivaciones(db):
    repositorio.set_parcel_active(1, False)
    assert repositorio.sensors_last_seen() == []
    repositorio.set_parcel_active(3, True)
    assert [code for code, _ in repositorio.sensors_last_seen()] == ["t003"]


# ---------------------------------------------------------------------------------------
# is_active en las parcelas
# ---------------------------------------------------------------------------------------


def test_las_parcelas_dicen_si_estan_activas(db):
    estados = {p.id: p.is_active for p in repositorio.list_parcels(include_inactive=True)}
    assert estados == {1: True, 2: True, 3: False}
    assert repositorio.get_parcel(3).is_active is False


def test_set_parcel_active_devuelve_el_estado_nuevo(db):
    assert repositorio.set_parcel_active(1, False).is_active is False
    assert repositorio.set_parcel_active(1, True).is_active is True


# ---------------------------------------------------------------------------------------
# Usuarios: búsquedas
# ---------------------------------------------------------------------------------------
# El fixture ``db`` ya trae el usuario 1: admin / a@x.es / password_hash="x".


def _new_user(**overrides):
    data = dict(username="ana", email="ana@x.es", role="tecnico", password_hash="hash-ana")
    data.update(overrides)
    return repositorio.create_user(**data)


def test_get_user_devuelve_el_modelo_con_password_hash(db):
    user = repositorio.get_user(1)
    assert isinstance(user, User)  # el modelo de la base de datos, no el esquema
    assert (user.username, user.password_hash, user.role) == ("admin", "x", "admin")


def test_get_user_se_puede_leer_con_la_sesion_cerrada(db):
    user = repositorio.get_user_by_username("admin")
    # Si siguiera ligado a una sesión cerrada, leer estos campos fallaría.
    assert user.email == "a@x.es" and user.is_active is True and user.created_at is not None


@pytest.mark.parametrize(
    "call",
    [
        lambda: repositorio.get_user(999),
        lambda: repositorio.get_user_by_username("nadie"),
        lambda: repositorio.get_user_by_email("nadie@x.es"),
        lambda: repositorio.get_user_by_google_sub("g-nadie"),
    ],
)
def test_busquedas_de_usuario_inexistente_devuelven_none(db, call):
    assert call() is None


def test_get_user_by_email_no_distingue_mayusculas_ni_espacios(db):
    assert repositorio.get_user_by_email("  A@X.ES ").id == 1


def test_get_user_by_google_sub(db):
    created = _new_user(username="gina", email="gina@x.es", password_hash=None, google_sub="g-123")
    user = repositorio.get_user_by_google_sub("g-123")
    assert user.id == created.id and user.password_hash is None


def test_list_users_por_orden_y_sin_contrasena(db):
    _new_user()
    users = repositorio.list_users()
    assert [u.username for u in users] == ["admin", "ana"]
    assert all(isinstance(u, s.User) for u in users)
    assert not hasattr(users[0], "password_hash")


def test_list_users_incluye_los_desactivados(db):
    created = _new_user()
    repositorio.update_user(created.id, {"is_active": False})
    assert [u.is_active for u in repositorio.list_users()] == [True, False]


# ---------------------------------------------------------------------------------------
# create_user
# ---------------------------------------------------------------------------------------


def test_create_user_con_contrasena(db):
    created = _new_user()
    assert isinstance(created, s.User) and created.id == 2
    assert (created.username, created.role, created.is_active) == ("ana", "tecnico", True)
    stored = repositorio.get_user(created.id)
    assert stored.password_hash == "hash-ana" and stored.email_verified is False


def test_create_user_solo_con_google(db):
    created = _new_user(password_hash=None, google_sub="g-1", email_verified=True)
    stored = repositorio.get_user(created.id)
    assert stored.password_hash is None and stored.google_sub == "g-1"
    assert stored.email_verified is True


def test_create_user_guarda_el_correo_en_minusculas(db):
    created = _new_user(email="  Ana@X.ES ")
    assert repositorio.get_user(created.id).email == "ana@x.es"


def test_create_user_sin_ninguna_credencial_lanza_value_error(db):
    with pytest.raises(ValueError):
        _new_user(password_hash=None, google_sub=None)
    assert len(repositorio.list_users()) == 1  # no se creó


@pytest.mark.parametrize("username", ["ana@x.es", "", "   "])
def test_create_user_rechaza_username_con_arroba_o_vacio(db, username):
    with pytest.raises(ValueError):
        _new_user(username=username)


def test_create_user_rechaza_un_rol_desconocido(db):
    with pytest.raises(ValueError):
        _new_user(role="jefe")


@pytest.mark.parametrize(
    "overrides",
    [
        {"username": "admin"},  # username repetido
        {"email": "A@X.es"},  # correo repetido aunque cambien las mayúsculas
    ],
)
def test_create_user_repetido_lanza_already_exists(db, overrides):
    with pytest.raises(repositorio.AlreadyExistsError):
        _new_user(**overrides)
    assert len(repositorio.list_users()) == 1


def test_create_user_google_sub_repetido_lanza_already_exists(db):
    _new_user(google_sub="g-1")
    with pytest.raises(repositorio.AlreadyExistsError):
        _new_user(username="otra", email="otra@x.es", google_sub="g-1")


def test_create_user_varios_sin_google_sub_no_chocan(db):
    # google_sub es único, pero vacío no cuenta como repetido.
    _new_user()
    _new_user(username="luis", email="luis@x.es")
    assert len(repositorio.list_users()) == 3


# ---------------------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------------------


def test_update_user_cambia_solo_lo_indicado(db):
    created = _new_user()
    result = repositorio.update_user(created.id, {"role": "lector"})
    assert result.role == "lector" and result.is_active is True
    assert repositorio.get_user(created.id).password_hash == "hash-ana"


def test_update_user_desactivar_y_verificar_son_cosas_distintas(db):
    created = _new_user()
    repositorio.update_user(created.id, {"email_verified": True})
    repositorio.update_user(created.id, {"is_active": False})
    stored = repositorio.get_user(created.id)
    assert stored.email_verified is True and stored.is_active is False


def test_update_user_cambia_la_contrasena(db):
    created = _new_user()
    repositorio.update_user(created.id, {"password_hash": "hash-nuevo"})
    assert repositorio.get_user(created.id).password_hash == "hash-nuevo"


def test_update_user_enlazar_y_desenlazar_google(db):
    created = _new_user()
    repositorio.update_user(created.id, {"google_sub": "g-9"})
    assert repositorio.get_user_by_google_sub("g-9").id == created.id
    repositorio.update_user(created.id, {"google_sub": None})  # aún tiene contraseña
    assert repositorio.get_user_by_google_sub("g-9") is None


def test_update_user_no_puede_quedarse_sin_credenciales(db):
    created = _new_user()  # solo contraseña
    with pytest.raises(ValueError):
        repositorio.update_user(created.id, {"password_hash": None})
    assert repositorio.get_user(created.id).password_hash == "hash-ana"


def test_update_user_google_sub_de_otro_lanza_already_exists(db):
    _new_user(google_sub="g-1")
    other = _new_user(username="luis", email="luis@x.es")
    with pytest.raises(repositorio.AlreadyExistsError):
        repositorio.update_user(other.id, {"google_sub": "g-1"})


def test_update_user_su_propio_google_sub_no_cuenta_como_repetido(db):
    created = _new_user(google_sub="g-1")
    assert repositorio.update_user(created.id, {"google_sub": "g-1"}) is not None


@pytest.mark.parametrize("field", ["username", "email", "id", "created_at", "otro"])
def test_update_user_rechaza_campos_no_editables(db, field):
    with pytest.raises(ValueError):
        repositorio.update_user(1, {field: "x"})


@pytest.mark.parametrize("field", ["role", "is_active", "email_verified"])
def test_update_user_no_admite_none_en_campos_obligatorios(db, field):
    with pytest.raises(ValueError):
        repositorio.update_user(1, {field: None})


def test_update_user_rechaza_un_rol_desconocido(db):
    with pytest.raises(ValueError):
        repositorio.update_user(1, {"role": "jefe"})
    assert repositorio.get_user(1).role == "admin"


def test_update_user_inexistente_devuelve_none(db):
    assert repositorio.update_user(999, {"role": "lector"}) is None


# ---------------------------------------------------------------------------------------
# Terreno: datos de prueba
# ---------------------------------------------------------------------------------------

ZONE_BODY = s.ZoneCreate(name="Bancal norte", type="crop", crop="aguacate", boundary=BOUNDARY)
TREE = s.ElementCreate(
    type="tree", subtype="aguacate", geometry=s.Geometry(type="Point", coordinates=[-3.0, 36.0]),
    height_m=4.5,
)
PATH = s.ElementCreate(
    type="path",
    geometry=s.Geometry(type="LineString", coordinates=[[-3.0, 36.0], [-2.95, 36.05]]),
)


def _add_tank(db_engine, parcel_id=1, name="Balsa", capacity=10000.0, sensor_id=None):
    with Session(db_engine) as session:
        row = Tank(parcel_id=parcel_id, name=name, capacity_l=capacity, level_sensor_id=sensor_id)
        session.add(row)
        session.commit()
        return row.id


@pytest.fixture
def nivel(db):
    """Un sensor de nivel de depósito (d001) en la parcela 1."""
    with Session(db) as session:
        session.add(Sensor(id="d001", parcel_id=1, type="nivel_deposito", unit="%"))
        session.commit()
    return "d001"


# ---------------------------------------------------------------------------------------
# create_zone / create_element / delete_element
# ---------------------------------------------------------------------------------------


def test_create_zone_guarda_y_devuelve_la_zona(db):
    zone = repositorio.create_zone(1, ZONE_BODY, 321.5)
    assert isinstance(zone, s.Zone) and zone.id == 1 and zone.parcel_id == 1
    assert (zone.name, zone.type, zone.crop, zone.area_m2) == ("Bancal norte", "crop", "aguacate", 321.5)
    assert zone.boundary == BOUNDARY  # vuelve como Polygon, no como texto


def test_create_zone_guarda_el_contorno_como_texto_geojson(db):
    repositorio.create_zone(1, ZONE_BODY, None)
    with Session(db) as session:
        stored = session.get(Zone, 1).boundary
    assert isinstance(stored, str) and s.Polygon.model_validate_json(stored) == BOUNDARY


def test_create_zone_parcela_inexistente_lanza_not_found(db):
    with pytest.raises(repositorio.NotFoundError):
        repositorio.create_zone(999, ZONE_BODY, 1.0)


def test_create_element_punto_y_linea(db):
    tree = repositorio.create_element(1, TREE)
    path = repositorio.create_element(1, PATH)
    assert isinstance(tree, s.TerrainElement)
    assert (tree.type, tree.subtype, tree.height_m) == ("tree", "aguacate", 4.5)
    assert tree.geometry == TREE.geometry and path.geometry == PATH.geometry
    assert path.subtype is None and path.height_m is None


def test_create_element_parcela_inexistente_lanza_not_found(db):
    with pytest.raises(repositorio.NotFoundError):
        repositorio.create_element(999, TREE)


def test_delete_element_borra_y_dice_si_existia(db):
    tree = repositorio.create_element(1, TREE)
    other = repositorio.create_element(1, PATH)
    assert repositorio.delete_element(tree.id) is True
    assert [e.id for e in repositorio.get_terrain(1).elements] == [other.id]  # el otro sigue
    assert repositorio.delete_element(tree.id) is False  # ya no existe


def test_delete_element_inexistente_devuelve_false(db):
    assert repositorio.delete_element(999) is False


# ---------------------------------------------------------------------------------------
# tanks
# ---------------------------------------------------------------------------------------


def test_tanks_saca_el_nivel_de_la_ultima_lectura_del_sensor(db, nivel):
    _add_tank(db, sensor_id=nivel)
    repositorio.save_reading(nivel, at(0), 90.0)
    repositorio.save_reading(nivel, at(5), 42.5)  # la más reciente
    (tank,) = repositorio.tanks(1)
    assert isinstance(tank, s.Tank)
    assert (tank.level_pct, tank.available_l, tank.capacity_l) == (42.5, 4250.0, 10000.0)


def test_tanks_usa_la_mas_reciente_aunque_se_guardara_antes(db, nivel):
    _add_tank(db, sensor_id=nivel)
    repositorio.save_reading(nivel, at(5), 30.0)
    repositorio.save_reading(nivel, at(1), 80.0)  # llega tarde, pero es más antigua
    assert repositorio.tanks(1)[0].level_pct == 30.0


def test_tanks_redondea_los_litros_a_un_decimal(db, nivel):
    _add_tank(db, capacity=333.0, sensor_id=nivel)
    repositorio.save_reading(nivel, at(0), 33.33)
    assert repositorio.tanks(1)[0].available_l == 111.0  # 110.9889 -> 111.0


@pytest.mark.parametrize("with_sensor", [False, True])  # sin sensor / sensor sin lecturas
def test_tanks_sin_dato_de_nivel_deja_none(db, nivel, with_sensor):
    _add_tank(db, sensor_id=nivel if with_sensor else None)
    tank = repositorio.tanks(1)[0]
    assert tank.level_pct is None and tank.available_l is None  # "no se sabe", no "vacío"


def test_tanks_un_nivel_cero_no_es_none(db, nivel):
    _add_tank(db, sensor_id=nivel)
    repositorio.save_reading(nivel, at(0), 0.0)
    tank = repositorio.tanks(1)[0]
    assert tank.level_pct == 0.0 and tank.available_l == 0.0


def test_tanks_varios_por_orden_y_solo_de_esa_parcela(db, nivel):
    first = _add_tank(db, name="Balsa", sensor_id=nivel)
    second = _add_tank(db, name="Aljibe")
    _add_tank(db, parcel_id=2, name="De otra parcela")
    assert [t.id for t in repositorio.tanks(1)] == [first, second]


@pytest.mark.parametrize("parcel_id", [2, 999])  # sin depósitos / inexistente
def test_tanks_sin_depositos_devuelve_lista_vacia(db, parcel_id):
    assert repositorio.tanks(parcel_id) == []


# ---------------------------------------------------------------------------------------
# get_terrain
# ---------------------------------------------------------------------------------------


def test_get_terrain_reune_todo_lo_de_la_parcela(db, nivel):
    zone = repositorio.create_zone(1, ZONE_BODY, 100.0)
    tree = repositorio.create_element(1, TREE)
    _add_tank(db, sensor_id=nivel)
    terrain = repositorio.get_terrain(1)
    assert isinstance(terrain, s.Terrain)
    assert isinstance(terrain.parcel, s.ParcelDetail) and terrain.parcel.boundary == BOUNDARY
    assert [z.id for z in terrain.zones] == [zone.id]
    assert [e.id for e in terrain.elements] == [tree.id]
    assert [x.id for x in terrain.sensors] == ["a001", "d001", "h001", "t001"]  # con desactivado
    assert [t.name for t in terrain.tanks] == ["Balsa"]


def test_get_terrain_no_mezcla_parcelas(db):
    repositorio.create_zone(1, ZONE_BODY, None)
    repositorio.create_element(1, TREE)
    terrain = repositorio.get_terrain(2)
    assert (terrain.zones, terrain.elements, terrain.sensors, terrain.tanks) == ([], [], [], [])


def test_get_terrain_de_una_parcela_de_baja(db):
    # Como get_parcel: pedir una parcela concreta no la oculta; ocultarla es cosa de la API.
    assert repositorio.get_terrain(3).parcel.is_active is False


def test_get_terrain_parcela_inexistente_devuelve_none(db):
    assert repositorio.get_terrain(999) is None
