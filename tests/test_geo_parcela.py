"""Centro de un polígono y esquema de «Añadir parcela» (el endpoint llega con ``create_parcel``)."""

import pytest
from pydantic import ValidationError

from demeter.api import schemas as s
from demeter.api.geo import offset, polygon_area_m2, polygon_centroid, rectangle


def test_el_centro_de_un_rectangulo_es_su_centro():
    lat, lon = polygon_centroid(rectangle(36.7452, -3.5101, 120, 80))
    assert (lat, lon) == pytest.approx((36.7452, -3.5101), abs=1e-6)


def test_el_centro_no_se_deja_llevar_por_los_vertices_de_un_lado():
    # Un rectángulo de 100×100 con 10 vértices extra pegados al lado oeste: la media de vértices
    # se iría al oeste, el centro de masas no se mueve.
    lat0, lon0 = 36.7, -3.4
    base = rectangle(lat0, lon0, 100, 100).coordinates[0][:-1]  # SO, SE, NE, NO
    extra = [offset(lat0, lon0, -50, y) for y in range(-40, 50, 9)]  # puntos sobre el lado oeste
    ring = [base[0], base[1], base[2], base[3], *reversed(extra)]
    ring.append(ring[0])
    poly = s.Polygon(coordinates=[ring])
    lat, lon = polygon_centroid(poly)
    media_lon = sum(p[0] for p in ring) / len(ring)
    assert abs(lon - lon0) < abs(media_lon - lon0) / 5
    assert (lat, lon) == pytest.approx((lat0, lon0), abs=2e-5)


def test_el_centro_de_una_l_esta_dentro_de_su_caja_y_se_desplaza_hacia_el_brazo_grueso():
    lat0, lon0 = 36.7, -3.4
    pts = [(0, 0), (100, 0), (100, 30), (30, 30), (30, 100), (0, 100)]  # una «L»
    ring = [offset(lat0, lon0, x, y) for x, y in pts]
    ring.append(ring[0])
    lat, lon = polygon_centroid(s.Polygon(coordinates=[ring]))
    sw = offset(lat0, lon0, 0, 0)
    ne = offset(lat0, lon0, 100, 100)
    assert sw[0] < lon < ne[0] and sw[1] < lat < ne[1]
    # el centro de masas de esa L está más cerca de la esquina del ángulo que el centro de la caja
    caja = offset(lat0, lon0, 50, 50)
    assert lon < caja[0] and lat < caja[1]


def test_el_orden_de_los_vertices_no_cambia_el_centro():
    poly = rectangle(36.7, -3.4, 100, 60, dx_m=300, dy_m=-120)
    reves = s.Polygon(coordinates=[list(reversed(poly.coordinates[0]))])
    a, b = polygon_centroid(poly), polygon_centroid(reves)
    assert a == pytest.approx(b, abs=1e-7)


def test_un_poligono_sin_superficie_da_la_media_y_uno_sin_vertices_suficientes_falla():
    linea = s.Polygon(coordinates=[[[0, 0], [1, 1], [2, 2], [0, 0]]])
    assert polygon_centroid(linea) == pytest.approx((0.75, 0.75), abs=1e-6)  # media de los 4 puntos del anillo
    with pytest.raises(ValueError):
        polygon_centroid(s.Polygon(coordinates=[[[0, 0], [1, 1], [0, 0]]]))


def test_centro_y_area_son_coherentes_con_el_desplazamiento():
    poly = rectangle(36.7, -3.4, 200, 50, dx_m=1000, dy_m=500)
    lat, lon = polygon_centroid(poly)
    esperado = offset(36.7, -3.4, 1000, 500)
    assert (lon, lat) == pytest.approx((esperado[0], esperado[1]), abs=2e-6)
    assert polygon_area_m2(poly) == pytest.approx(10000, rel=0.01)


# ---------------------------------------------------------------- esquema ParcelCreate


def body(**extra):
    return {"name": "Huerta nueva", "location": "Motril", "crop": "mango", **extra}


def test_se_crea_con_contorno_o_con_centro():
    s.ParcelCreate(**body(boundary=rectangle(36.7, -3.4, 50, 50).model_dump()))
    s.ParcelCreate(**body(latitude=36.7, longitude=-3.4))


def test_sin_contorno_ni_centro_o_con_el_centro_a_medias_falla():
    for malo in (body(), body(latitude=36.7), body(longitude=-3.4)):
        with pytest.raises(ValidationError):
            s.ParcelCreate(**malo)


def test_los_textos_se_recortan_y_no_pueden_quedar_vacios():
    p = s.ParcelCreate(**body(name="  Huerta  ", latitude=1, longitude=1))
    assert p.name == "Huerta"
    for campo in ("name", "location", "crop"):
        with pytest.raises(ValidationError):
            s.ParcelCreate(**{**body(latitude=1, longitude=1), campo: "   "})
        with pytest.raises(ValidationError):
            s.ParcelCreate(**{**body(latitude=1, longitude=1), campo: ""})


@pytest.mark.parametrize("extra", [{"latitude": 95, "longitude": 0}, {"latitude": 0, "longitude": -200},
                                   {"name": "x" * 101, "latitude": 0, "longitude": 0}])
def test_coordenadas_y_longitudes_fuera_de_rango_fallan(extra):
    with pytest.raises(ValidationError):
        s.ParcelCreate(**{**body(), **extra})
