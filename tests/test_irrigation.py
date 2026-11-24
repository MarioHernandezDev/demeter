"""Pruebas del recomendador de riego (E5, issue #7) y del reparto de agua (idea #56).

Reglas de docs/insights-contrato.md §2.
"""

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from demeter.api import schemas as s
from demeter.api.geo import offset, rectangle
from demeter.services.irrigation import (
    available_water,
    best_start,
    crop_kc,
    distribution_options,
    et0_hargreaves,
    point_in_polygon,
    recommend,
    split_water,
)

LAT, LON = 36.7174, -3.4301
NOW = datetime(2026, 11, 24, 10, 0, tzinfo=timezone.utc)  # 11:00 en Motril
MADRID = ZoneInfo("Europe/Madrid")


def zona(id, crop="aguacate", w=100, h=50, dx=0, dy=0, tipo="crop"):
    b = rectangle(LAT, LON, w, h, dx, dy)
    return s.Zone(id=id, parcel_id=1, name=f"Zona {id}", type=tipo, crop=crop, boundary=b, area_m2=w * h)


def suelo(id, valor, dx=0, dy=0, low=25.0, high=60.0):
    lon, lat = offset(LAT, LON, dx, dy)
    return s.Sensor(id=id, parcel_id=1, type="humedad_suelo", unit="%", threshold_low=low,
                    threshold_high=high, latitude=lat, longitude=lon), valor


def tiempo(lluvia_prob=10.0, lluvia_mm=0.0, t_min=12.0, t_max=22.0):
    """24 h de previsión; la lluvia total se reparte entre todas las horas."""
    horas = []
    for k in range(1, 25):
        t = NOW + timedelta(hours=k)
        temp = t_min + (t_max - t_min) * (0.5 + 0.5 * math.sin((t.hour - 9) / 24 * 6.283))
        horas.append(s.WeatherHour(time=t, temperature_c=round(temp, 1), rain_probability_pct=lluvia_prob,
                                   rain_mm=lluvia_mm / 24))
    return horas


def deposito(litros, capacidad=20000.0, id=1):
    return s.Tank(id=id, parcel_id=1, name=f"D{id}", capacity_l=capacidad,
                  level_pct=100 * litros / capacidad, available_l=litros)


def consejo(zonas=None, sensores=None, prevision=None, depositos=None, **kw):
    return recommend(
        1,
        zonas if zonas is not None else [zona(1)],
        sensores if sensores is not None else [suelo("h1", 20.0)],
        prevision if prevision is not None else tiempo(),
        depositos if depositos is not None else [deposito(20000)],
        NOW, latitude=LAT, **kw,
    )


# ------------------------------------------------------------------ decisiones


def test_suelo_seco_y_sin_lluvia_riega():
    a = consejo()
    assert a.action == "irrigate"
    assert len(a.zones) == 1 and a.zones[0].liters > 0
    assert a.total_liters == pytest.approx(sum(z.liters for z in a.zones))
    assert a.enough_water and a.available_l == 20000
    assert "Regar" in a.summary


def test_suelo_humedo_espera():
    a = consejo(sensores=[suelo("h1", 45.0)])
    assert a.action == "wait"
    assert a.zones == [] and a.total_liters == 0
    assert "45" in a.summary


def test_lluvia_probable_no_riega():
    a = consejo(prevision=tiempo(lluvia_prob=90, lluvia_mm=8))
    assert a.action == "skip"
    assert a.zones == [] and a.total_liters == 0
    assert "lluvia" in a.summary.lower()


def test_lluvia_poco_probable_no_impide_regar_pero_se_descuenta():
    seco = consejo()
    con_algo = consejo(prevision=tiempo(lluvia_prob=40, lluvia_mm=1))
    assert con_algo.action == "irrigate"
    assert con_algo.total_liters < seco.total_liters
    assert "descuenta" in con_algo.summary


def test_sin_sensor_de_suelo_espera():
    a = consejo(sensores=[])
    assert a.action == "wait"
    assert a.factors.soil_moisture_pct is None


def test_sin_prevision_espera():
    a = consejo(prevision=[])
    assert a.action == "wait"
    assert a.factors.rain_probability_pct is None


def test_sin_agua_en_los_depositos_espera():
    a = consejo(depositos=[])
    assert a.action == "wait"
    assert a.available_l == 0 and a.factors.tank_level_pct is None


def test_solo_riega_zonas_de_cultivo():
    a = consejo(zonas=[zona(1), zona(2, crop=None, tipo="no_crop", dy=60)])
    assert [z.zone_id for z in a.zones] == [1]


# ------------------------------------------------------------------ cantidades


def test_nunca_pide_mas_agua_de_la_que_hay():
    a = consejo(zonas=[zona(1, w=200, h=100)], depositos=[deposito(500)])
    assert a.action == "irrigate"
    assert a.total_liters <= 500
    assert a.enough_water
    assert "recortado" in a.summary


def test_mas_seco_pide_mas_agua():
    poco = consejo(sensores=[suelo("h1", 29.0)])
    mucho = consejo(sensores=[suelo("h1", 15.0)])
    assert mucho.total_liters > poco.total_liters


def test_mas_calor_pide_mas_agua():
    fresco = consejo(prevision=tiempo(t_min=10, t_max=18))
    calor = consejo(prevision=tiempo(t_min=22, t_max=36))
    assert calor.total_liters > fresco.total_liters


def test_cultivo_que_mas_bebe_recibe_mas_por_m2():
    a = consejo(zonas=[zona(1, "aguacate", dy=30), zona(2, "tomate", dy=-30)],
                sensores=[suelo("h1", 20.0)])
    por_m2 = {z.zone_id: z.liters for z in a.zones}
    assert por_m2[2] > por_m2[1]  # misma superficie, el tomate (Kc 1,05) bebe más


def test_cantidades_razonables_para_goteo():
    a = consejo()
    litros_m2 = a.total_liters / 5000
    assert 0.5 < litros_m2 < 8  # unos pocos L/m² al día, no una inundación


def test_cada_zona_usa_su_sensor():
    zonas = [zona(1, dy=30), zona(2, dy=-30)]
    a = consejo(zonas=zonas, sensores=[suelo("h1", 45.0, dy=30), suelo("h2", 18.0, dy=-30)])
    assert [z.zone_id for z in a.zones] == [2]  # la zona 1 está húmeda


# ------------------------------------------------------------------ horario


def test_empieza_a_primera_hora_local_y_zonas_en_cadena():
    a = consejo(zonas=[zona(1, dy=30), zona(2, dy=-30)], sensores=[suelo("h1", 20.0)])
    primero, segundo = a.zones
    local = primero.start_at.astimezone(MADRID)
    assert 5 <= local.hour <= 8 and primero.start_at > NOW
    assert segundo.start_at == primero.start_at + timedelta(minutes=primero.duration_min)
    assert primero.duration_min == pytest.approx(primero.liters / 300, abs=1)


def test_elige_la_hora_mas_fresca_de_la_franja():
    prevision = tiempo()
    for h in prevision:
        if h.time.astimezone(MADRID).hour == 7:
            h.temperature_c = -5
    assert best_start(NOW, prevision).astimezone(MADRID).hour == 7


def test_si_aun_es_de_madrugada_riega_hoy():
    temprano = datetime(2026, 11, 24, 3, 0, tzinfo=timezone.utc)  # 4:00 en Motril
    t = best_start(temprano, [])
    assert t.date() == temprano.date() and t > temprano


# ------------------------------------------------------------------ piezas sueltas


def test_et0_de_noviembre_en_motril():
    et0 = et0_hargreaves(12, 22, LAT, 328)
    assert 1.0 < et0 < 3.0  # mm/día, valor típico de otoño en la costa
    assert et0_hargreaves(20, 34, LAT, 196) > 5  # julio


def test_kc_por_cultivo():
    assert crop_kc("Tomate") > crop_kc("aguacate")
    assert crop_kc(None) == crop_kc("desconocido")


def test_punto_dentro_del_poligono():
    z = zona(1)
    assert point_in_polygon(*offset(LAT, LON, 0, 0), z.boundary)
    assert not point_in_polygon(*offset(LAT, LON, 0, 100), z.boundary)


# ------------------------------------------------------------------ reparto del agua (#56)


def test_suma_de_varios_depositos():
    litros, nivel = available_water([deposito(10000, 20000, 1), deposito(2500, 5000, 2)])
    assert litros == 12500 and nivel == 50.0


def test_reparto_proporcional():
    assert split_water({1: 3, 2: 1}, 1000) == {1: 750.0, 2: 250.0}


def test_reparto_con_tope_pasa_lo_que_sobra_a_los_demas():
    r = split_water({1: 1, 2: 1}, 1000, cap={1: 100, 2: 5000})
    assert r == {1: 100.0, 2: 900.0}


def test_reparto_nunca_supera_lo_disponible():
    r = split_water({1: 1, 2: 2, 3: 3}, 10)
    assert sum(r.values()) <= 10


def test_opciones_de_reparto():
    zonas = [zona(1, "aguacate", 100, 50), zona(2, "tomate", 100, 50, dy=60), zona(3, None, tipo="no_crop")]
    planes = {p.criterion: p for p in distribution_options(zonas, 10000, needs_l={1: 1000, 2: 3000})}
    assert planes["superficie"].liters == {1: 5000.0, 2: 5000.0}
    assert planes["cultivo"].liters[2] > planes["cultivo"].liters[1]
    assert planes["necesidad"].liters == {1: 1000.0, 2: 3000.0}  # sobra agua: se queda en el depósito
    assert all(3 not in p.liters for p in planes.values())
