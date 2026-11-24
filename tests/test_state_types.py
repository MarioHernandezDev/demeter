"""Pruebas del contrato de tipos de la interfaz (C1, issue #28)."""

from demeter.state.types import (
    Alert,
    DashboardSummary,
    HistoryQuery,
    Reading,
    Sensor,
    SensorSnapshot,
    SensorStatus,
)
from demeter.theme import COLORES, ESTADOS_SENSOR, estado_sensor

SENSOR = {
    "id": "h001", "parcel_id": 1, "type": "humedad_suelo", "unit": "%",
    "description": "Bancal 3", "threshold_low": 25.0, "threshold_high": 60.0,
}


def test_reading_acepta_el_ejemplo_del_reto_y_ignora_claves_nuevas():
    r = Reading.from_api({
        "sensor_id": "t001", "timestamp": "2025-10-10T12:34:56Z",
        "type": "temperatura", "value": 23.7, "unit": "ºC", "campo_nuevo": 1,
    })
    assert r.value == 23.7 and r.unit == "ºC"


def test_estado_del_sensor_frente_a_umbrales():
    s = Sensor.from_api(SENSOR)
    assert s.status_for(19) == SensorStatus.LOW.value
    assert s.status_for(40) == SensorStatus.OK.value
    assert s.status_for(61) == SensorStatus.HIGH.value
    assert s.status_for(None) == SensorStatus.SIN_DATOS.value


def test_sensor_sin_umbral_alto():
    s = Sensor.from_api({**SENSOR, "threshold_high": None})
    assert s.status_for(1000) == SensorStatus.OK.value


def test_dashboard_calcula_estado_y_alertas_sin_leer():
    d = DashboardSummary.from_api({
        "parcel": {"id": 1, "name": "Finca La Costa", "location": "Carchuna, Motril"},
        "sensors": [{"sensor": SENSOR, "last": {"sensor_id": "h001", "timestamp": "2026-11-16T10:02:00Z", "value": 19}}],
        "alerts": [
            {"id": 1, "sensor_id": "h001", "timestamp": "2026-11-16T10:02:00Z", "type": "LOW", "message": "19 %"},
            {"id": 2, "sensor_id": "t001", "timestamp": "2026-11-15T14:40:00Z", "type": "HIGH", "message": "36 ºC", "acknowledged": True},
        ],
    })
    assert d.sensors[0].status == "LOW"
    assert d.unread_alerts == 1
    assert isinstance(d.alerts[0], Alert)


def test_parametros_del_historico():
    assert HistoryQuery("h001").params() == {"limit": 500}
    q = HistoryQuery("h001", from_="2026-11-09T00:00:00Z", to="2026-11-16T00:00:00Z", limit=100)
    assert q.params() == {"limit": 100, "from": "2026-11-09T00:00:00Z", "to": "2026-11-16T00:00:00Z"}


def test_offline_llega_de_la_api_y_gana_a_los_umbrales():
    snap = SensorSnapshot.from_api({
        "sensor": SENSOR, "status": "offline", "recent": [30, 22, 19],
        "last": {"sensor_id": "h001", "timestamp": "2026-11-24T09:00:00Z", "value": 19},
    })
    assert snap.status == SensorStatus.OFFLINE.value and snap.offline
    assert snap.recent == [30.0, 22.0, 19.0]
    # Sin «status» la interfaz solo puede mirar umbrales: nunca deduce offline.
    assert not SensorSnapshot.from_api({"sensor": SENSOR}).offline
    assert SensorSnapshot.from_api({"sensor": SENSOR}).recent == []


def test_alerta_offline_y_campos_nuevos():
    a = Alert.from_api({
        "id": 3, "sensor_id": "h001", "timestamp": "2026-11-24T09:10:00Z",
        "type": "OFFLINE", "message": "Sin señal", "resolved_at": None,
    })
    assert a.active and a.value is None and a.threshold is None
    b = Alert.from_api({
        "id": 4, "sensor_id": "h001", "timestamp": "2026-11-24T09:10:00Z", "type": "LOW",
        "message": "19 %", "value": 19, "threshold": 25, "resolved_at": "2026-11-24T09:30:00Z",
    })
    assert not b.active and b.threshold == 25


def test_cada_estado_tiene_como_pintarse():
    assert set(ESTADOS_SENSOR) == {s.value for s in SensorStatus}
    assert all(e["color"] in COLORES for e in ESTADOS_SENSOR.values())
    assert estado_sensor("offline")["clase"] == "off"
    assert estado_sensor("raro") == ESTADOS_SENSOR["sin_datos"]
