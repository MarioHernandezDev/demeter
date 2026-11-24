"""Pruebas del motor de predicción a 24 h (E4, issue #5). Reglas de docs/insights-contrato.md §1."""

import math
from datetime import datetime, timedelta, timezone

import pytest

from demeter.api import schemas as s
from demeter.services.forecast import (
    MODEL_DAILY,
    MODEL_TREND,
    forecast,
    hourly_means,
    predict_sensor,
)

NOW = datetime(2026, 11, 24, 10, 20, tzinfo=timezone.utc)


def serie(fn, horas: float = 24, cada_min: int = 10):
    """Lecturas desde hace ``horas`` hasta ``NOW``, una cada ``cada_min`` minutos."""
    n = int(horas * 60 / cada_min)
    return [(NOW - timedelta(minutes=i * cada_min), fn(NOW - timedelta(minutes=i * cada_min)))
            for i in range(n, -1, -1)]


def sensor(tipo="humedad_suelo", unidad="%", low=25.0, high=60.0, id="h001"):
    return s.Sensor(id=id, parcel_id=1, type=tipo, unit=unidad, threshold_low=low, threshold_high=high)


def recta(ahora: float, por_hora: float):
    """Magnitud que vale ``ahora`` en ``NOW`` y cambia ``por_hora`` cada hora."""
    return lambda t: ahora + por_hora * ((t - NOW) / timedelta(hours=1))


def temperatura(t: datetime) -> float:
    hora = t.hour + t.minute / 60
    return 22 + 6 * math.sin(2 * math.pi * (hora - 9) / 24)


# ------------------------------------------------------------------ forma del contrato


def test_siempre_24_puntos_horarios_desde_la_proxima_hora():
    p = predict_sensor(sensor(), serie(lambda t: 40.0), NOW)
    assert len(p.points) == 24
    assert p.points[0].time == datetime(2026, 11, 24, 11, 0, tzinfo=timezone.utc)
    assert all(b.time - a.time == timedelta(hours=1) for a, b in zip(p.points, p.points[1:]))
    assert p.horizon_hours == 24 and p.step_minutes == 60
    assert p.generated_at == NOW


def test_banda_contiene_el_valor_y_se_ensancha():
    p = predict_sensor(sensor(), serie(lambda t: 40.0 + 0.3 * math.sin(t.minute)), NOW)
    assert all(x.lower <= x.value <= x.upper for x in p.points)
    ancho = [x.upper - x.lower for x in p.points]
    assert ancho[-1] > ancho[0] > 0  # nunca es una línea y crece con el tiempo


def test_porcentajes_recortados_a_0_100():
    # Suelo que se seca muy rápido: la recta bajaría de 0.
    seca = recta(10, -2)
    p = predict_sensor(sensor(low=None), serie(seca, horas=6), NOW)
    assert all(0 <= x.lower <= x.value <= x.upper <= 100 for x in p.points)
    assert p.points[-1].value == 0


def test_sin_datos_suficientes_devuelve_none():
    assert predict_sensor(sensor(), [], NOW) is None
    assert predict_sensor(sensor(), serie(lambda t: 40.0, horas=1), NOW) is None  # 2 horas distintas


def test_sensor_callado_hace_horas_no_se_predice():
    viejas = [(t - timedelta(hours=5), v) for t, v in serie(lambda t: 40.0)]
    assert predict_sensor(sensor(), viejas, NOW) is None


def test_ignora_lecturas_del_futuro():
    futuras = [(NOW + timedelta(hours=h), 99.0) for h in range(1, 5)]
    p = predict_sensor(sensor(), serie(lambda t: 40.0) + futuras, NOW)
    assert p.points[0].value == pytest.approx(40.0, abs=0.1)


def test_acepta_fechas_sin_zona_como_utc():
    naive = [(t.replace(tzinfo=None), v) for t, v in serie(lambda t: 40.0)]
    assert predict_sensor(sensor(), naive, NOW.replace(tzinfo=None)) is not None


# ------------------------------------------------------------------ modelos


def test_tendencia_prolonga_el_secado_del_suelo():
    # Baja 0,5 puntos por hora: dentro de 24 h estará 12 puntos más abajo.
    seca = recta(40, -0.5)
    p = predict_sensor(sensor(low=10), serie(seca), NOW)
    assert p.model == MODEL_TREND
    assert p.trend == "falling"
    assert p.points[-1].value == pytest.approx(seca(p.points[-1].time), abs=0.6)


def test_ciclo_diario_repite_la_curva_de_ayer():
    p = predict_sensor(sensor("temperatura", "ºC", 8, 35, "t001"), serie(temperatura, horas=30), NOW)
    assert p.model == MODEL_DAILY
    for x in p.points:
        assert x.value == pytest.approx(temperatura(x.time), abs=0.6)


def test_ciclo_diario_con_poca_historia_usa_la_tendencia():
    p = predict_sensor(sensor("temperatura", "ºC", 8, 35, "t001"), serie(temperatura, horas=8), NOW)
    assert p.model == MODEL_TREND


def test_ciclo_diario_corrige_si_hoy_hace_mas_calor_que_ayer():
    # Hoy (últimas horas) 3 ºC por encima de ayer: las primeras horas previstas lo reflejan.
    def calida(t):
        return temperatura(t) + (3 if NOW - t < timedelta(hours=4) else 0)

    p = predict_sensor(sensor("temperatura", "ºC", 8, 35, "t001"), serie(calida, horas=30), NOW)
    primero = p.points[0]
    assert primero.value > temperatura(primero.time) + 2
    # 19 h después la diferencia casi se ha olvidado (su hora de ayer no era de las cálidas).
    madrugada = next(x for x in p.points if x.time.hour == 5)
    assert madrugada.value < temperatura(madrugada.time) + 1


def test_media_por_hora():
    t = datetime(2026, 11, 24, 9, 0, tzinfo=timezone.utc)
    h = hourly_means([(t - timedelta(minutes=20), 1.0), (t + timedelta(minutes=20), 3.0),
                      (t + timedelta(minutes=40), 5.0)])
    assert h == {t: 2.0, t + timedelta(hours=1): 5.0}  # cada lectura cuenta en su hora más cercana


# ------------------------------------------------------------------ tendencia y cruce de umbral


def test_estable_si_cambia_menos_del_5_por_ciento_del_rango():
    p = predict_sensor(sensor(), serie(lambda t: 40.0), NOW)
    assert p.trend == "stable"
    assert p.crossing is None


def test_avisa_del_primer_cruce_de_umbral():
    # 30 % y bajando 1 punto por hora: cruza 25 % (LOW) hacia las 5-6 h.
    seca = recta(30, -1)
    p = predict_sensor(sensor(), serie(seca), NOW)
    assert p.crossing is not None
    assert p.crossing.type == "LOW"
    assert p.crossing.value < 25
    assert NOW + timedelta(hours=4) < p.crossing.at < NOW + timedelta(hours=8)
    previos = [x for x in p.points if x.time < p.crossing.at]
    assert all(x.value >= 25 for x in previos)


def test_cruce_alto():
    sube = recta(55, 1)
    p = predict_sensor(sensor(), serie(sube), NOW)
    assert p.crossing.type == "HIGH" and p.trend == "rising"


def test_sin_cruce_si_ya_esta_fuera_de_umbral():
    seca = recta(20, -1)
    p = predict_sensor(sensor(), serie(seca), NOW)
    assert p.crossing is None  # ya hay una alerta LOW activa


def test_sin_umbrales_no_hay_cruce():
    p = predict_sensor(sensor(low=None, high=None), serie(lambda t: 40.0), NOW)
    assert p.crossing is None


def test_forecast_devuelve_modelo_y_puntos():
    modelo, puntos = forecast(serie(lambda t: 40.0), NOW, daily=False)
    assert modelo == MODEL_TREND and len(puntos) == 24
