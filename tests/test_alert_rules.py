"""Pruebas de las reglas de alertas (D1, issue #36). Ejemplos de docs/alertas-contrato.md."""

from datetime import datetime, timedelta, timezone

import pytest

from demeter.services.alert_rules import (
    AlertKind,
    Decision,
    card_status,
    decide,
    is_offline,
    margin,
    message,
)
from demeter.state.types import Sensor

LOW, HIGH = AlertKind.LOW, AlertKind.HIGH
# h001 · humedad del suelo · umbrales 25–60 % → margen 0,7 puntos
H_LOW, H_HIGH = 25.0, 60.0
NOW = datetime(2026, 11, 16, 11, 2, tzinfo=timezone.utc)


def test_margen_es_el_2_por_ciento_del_rango():
    assert margin(25, 60) == pytest.approx(0.7)
    assert margin(8, 35) == pytest.approx(0.54)
    assert margin(30, 85) == pytest.approx(1.1)
    assert margin(None, 100) == pytest.approx(2)
    assert margin(20, None) == pytest.approx(0.4)
    assert margin(None, None) == 0


def test_secuencia_del_documento_abre_no_duplica_y_cierra_con_histeresis():
    pasos = [
        (None, 26.0, Decision()),                # normal
        (None, 24.8, Decision(open=LOW)),        # abre
        (LOW, 24.6, Decision()),                 # ya hay una activa: no duplica
        (LOW, 25.3, Decision()),                 # dentro del margen: sigue abierta
        (LOW, 25.7, Decision(close=LOW)),        # 25 + 0,7: cierra
    ]
    for active, value, esperado in pasos:
        assert decide(active, value, H_LOW, H_HIGH) == esperado, value


def test_el_umbral_exacto_es_normal():
    assert decide(None, 25.0, H_LOW, H_HIGH).nothing
    assert decide(None, 60.0, H_LOW, H_HIGH).nothing


def test_high_cierra_al_bajar_del_umbral_menos_el_margen():
    assert decide(HIGH, 59.5, H_LOW, H_HIGH).nothing
    assert decide(HIGH, 59.3, H_LOW, H_HIGH) == Decision(close=HIGH)


def test_salto_de_bajo_a_alto_cierra_una_y_abre_otra():
    assert decide(LOW, 70, H_LOW, H_HIGH) == Decision(close=LOW, open=HIGH)


def test_si_el_admin_quita_el_umbral_la_alerta_se_cierra():
    assert decide(HIGH, 75, H_LOW, None) == Decision(close=HIGH)


def test_offline_a_los_10_minutos():
    assert not is_offline(NOW - timedelta(minutes=9, seconds=59), NOW)
    assert is_offline(NOW - timedelta(minutes=10), NOW)
    assert not is_offline(None, NOW)  # nunca envió datos: «sin datos», no offline


def test_offline_no_pasa_por_decide():
    with pytest.raises(ValueError):
        decide(AlertKind.OFFLINE, 30, H_LOW, H_HIGH)


def test_semaforo_de_la_tarjeta_coincide_con_status_for_del_frontend():
    s = Sensor(id="h001", parcel_id=1, type="humedad_suelo", unit="%",
               threshold_low=H_LOW, threshold_high=H_HIGH)
    for value in (19, 25, 40, 60, 61):
        assert card_status(value, NOW, NOW, H_LOW, H_HIGH) == s.status_for(value)
    assert card_status(None, None, NOW, H_LOW, H_HIGH) == "sin_datos"
    assert card_status(19, NOW - timedelta(minutes=15), NOW, H_LOW, H_HIGH) == "offline"


def test_mensajes_como_en_los_wireframes():
    assert message(LOW, 19, "%", 25) == "19 % por debajo del umbral (25 %)"
    assert message(HIGH, 36, "ºC", 35) == "36 ºC por encima del umbral (35 ºC)"
    assert message(HIGH, 23.75, "ºC", 23.5) == "23,8 ºC por encima del umbral (23,5 ºC)"
    assert message(AlertKind.OFFLINE) == "Sin datos desde hace más de 10 min"
