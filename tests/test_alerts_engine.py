"""Pruebas del motor de alertas (D2, issue #37) sobre SQLite en memoria.

Casos de docs/alertas-contrato.md (secciones 3, 4 y 5).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select

from demeter.db.conexion import make_engine
from demeter.models import Alert, Parcel, Sensor, User
from demeter.services.alerts import (
    alertas_activas,
    utc,
    cerrar_alertas_sensor,
    comprobar_offline,
    evaluar_lectura,
)

T0 = datetime(2026, 11, 16, 11, 0, tzinfo=timezone.utc)


def minuto(n: int) -> datetime:
    return T0 + timedelta(minutes=n)


@pytest.fixture
def db():
    engine = make_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(User(id=1, username="admin", email="a@a", role="admin",
                         password_hash="x"))
        session.flush()
        session.add(Parcel(id=1, owner_id=1, name="Finca", location="Motril", crop="aguacate",
                           latitude=36.7, longitude=-3.5))
        session.flush()
        # h001: humedad del suelo 25–60 % → margen 0,7
        session.add(Sensor(id="h001", parcel_id=1, type="humedad_suelo", unit="%",
                           threshold_low=25, threshold_high=60))
        session.add(Sensor(id="x001", parcel_id=1, type="luminosidad", unit="klx"))
        session.commit()
        yield session


def lectura(db, sensor_id, n, valor):
    """Simula la ingesta: actualiza last_seen_at y llama al motor."""
    sensor = db.get(Sensor, sensor_id)
    cuando = minuto(n)
    abiertas = evaluar_lectura(db, sensor_id, cuando, valor)
    if sensor.last_seen_at is None or cuando > utc(sensor.last_seen_at):
        sensor.last_seen_at = cuando
    db.commit()
    return abiertas


def activas(db, sensor_id="h001"):
    return sorted(alertas_activas(db, sensor_id))


def test_secuencia_del_contrato_h001(db):
    assert lectura(db, "h001", 0, 26.0) == []
    abiertas = lectura(db, "h001", 1, 24.8)
    assert [a.type for a in abiertas] == ["LOW"]
    assert abiertas[0].message == "24,8 % por debajo del umbral (25 %)"
    assert abiertas[0].value == 24.8 and abiertas[0].threshold == 25
    assert abiertas[0].opened_at == minuto(1)

    assert lectura(db, "h001", 2, 24.6) == []          # no duplica
    assert lectura(db, "h001", 3, 25.3) == []          # dentro, pero sin margen
    assert activas(db) == ["LOW"]
    assert lectura(db, "h001", 4, 25.7) == []          # cierra
    assert activas(db) == []

    abiertas = lectura(db, "h001", 5, 24.0)            # se sale otra vez: alerta nueva
    assert [a.type for a in abiertas] == ["LOW"]
    assert len(db.exec(select(Alert)).all()) == 2


def test_cierra_low_y_abre_high_en_el_mismo_paso(db):
    lectura(db, "h001", 0, 20.0)
    abiertas = lectura(db, "h001", 1, 70.0)
    assert [a.type for a in abiertas] == ["HIGH"]
    assert abiertas[0].message == "70 % por encima del umbral (60 %)"
    assert activas(db) == ["HIGH"]
    low = db.exec(select(Alert).where(Alert.type == "LOW")).one()
    assert low.resolved_at == minuto(1)


def test_valor_justo_en_el_umbral_no_abre(db):
    assert lectura(db, "h001", 0, 25.0) == []
    assert lectura(db, "h001", 1, 60.0) == []


def test_sensor_sin_umbrales_nunca_abre_low_high(db):
    assert lectura(db, "x001", 0, 1e6) == []


def test_lectura_antigua_no_se_evalua(db):
    lectura(db, "h001", 10, 30.0)
    assert lectura(db, "h001", 5, 10.0) == []
    assert activas(db) == []


def test_sensor_desactivado_no_se_evalua_y_cierra_sus_alertas(db):
    lectura(db, "h001", 0, 10.0)
    assert cerrar_alertas_sensor(db, "h001", minuto(1)) == 1
    db.get(Sensor, "h001").is_active = False
    db.commit()
    assert lectura(db, "h001", 2, 10.0) == []
    assert activas(db) == []


def test_umbral_quitado_cierra_la_alerta_con_la_siguiente_lectura(db):
    lectura(db, "h001", 0, 10.0)
    db.get(Sensor, "h001").threshold_low = None
    db.commit()
    lectura(db, "h001", 1, 10.0)
    assert activas(db) == []


def test_offline_a_los_10_minutos_y_sin_duplicar(db):
    lectura(db, "h001", 0, 30.0)
    assert comprobar_offline(db, minuto(9)) == []
    abiertas = comprobar_offline(db, minuto(10))
    assert [(a.sensor_id, a.type) for a in abiertas] == [("h001", "OFFLINE")]
    assert abiertas[0].message == "Sin datos desde hace más de 10 min"
    assert abiertas[0].value is None and abiertas[0].threshold is None
    db.commit()
    assert comprobar_offline(db, minuto(11)) == []     # no duplica


def test_sensor_que_nunca_envio_datos_no_es_offline(db):
    assert comprobar_offline(db, minuto(60)) == []


def test_sensor_o_parcela_inactivos_no_quedan_offline(db):
    lectura(db, "h001", 0, 30.0)
    db.get(Parcel, 1).is_active = False
    db.commit()
    assert comprobar_offline(db, minuto(30)) == []
    db.get(Parcel, 1).is_active = True
    db.get(Sensor, "h001").is_active = False
    db.commit()
    assert comprobar_offline(db, minuto(30)) == []


def test_cualquier_lectura_cierra_offline_y_respeta_las_de_umbral(db):
    lectura(db, "h001", 0, 10.0)                       # LOW
    comprobar_offline(db, minuto(15))
    db.commit()
    assert activas(db) == ["LOW", "OFFLINE"]
    lectura(db, "h001", 16, 24.9)                      # vuelve, aún bajo
    assert activas(db) == ["LOW"]


def test_fechas_con_y_sin_zona_horaria_son_equivalentes(db):
    lectura(db, "h001", 0, 30.0)
    sin_zona = minuto(10).replace(tzinfo=None)
    assert len(comprobar_offline(db, sin_zona)) == 1


def test_la_bd_impide_dos_alertas_activas_del_mismo_tipo(db):
    for _ in range(2):
        db.add(Alert(sensor_id="h001", type="LOW", opened_at=minuto(0), message="x"))
    with pytest.raises(IntegrityError):
        db.commit()
