"""Geometría básica sin dependencias: superficie de un polígono en m² y utilidades de ejemplo.

La superficie se calcula proyectando latitud/longitud a metros alrededor del centro del
polígono (proyección equirrectangular) y aplicando la fórmula del área de Gauss. Para una
parcela (cientos de metros) el error es muy inferior al 0,1 %, de sobra para el editor 3D.
Si algún día hiciera falta precisión topográfica, se cambia esta función por una con
``pyproj`` sin tocar el resto de la API.
"""

import math

from demeter.api.schemas import Polygon

EARTH_RADIUS_M = 6_371_008.8


def polygon_area_m2(polygon: Polygon) -> float:
    """Superficie en m² del anillo exterior de un polígono GeoJSON (``[lon, lat]``)."""
    ring = polygon.coordinates[0]
    if len(ring) < 4:
        raise ValueError("un polígono necesita al menos 3 vértices distintos y el cierre")
    lat0 = math.radians(sum(p[1] for p in ring) / len(ring))
    xs = [EARTH_RADIUS_M * math.radians(p[0]) * math.cos(lat0) for p in ring]
    ys = [EARTH_RADIUS_M * math.radians(p[1]) for p in ring]
    twice_area = sum(xs[i] * ys[i + 1] - xs[i + 1] * ys[i] for i in range(len(ring) - 1))
    return round(abs(twice_area) / 2, 1)


def offset(lat: float, lon: float, dx_m: float, dy_m: float) -> list[float]:
    """Punto ``[lon, lat]`` situado ``dx_m`` metros al este y ``dy_m`` al norte de (lat, lon)."""
    dlat = math.degrees(dy_m / EARTH_RADIUS_M)
    dlon = math.degrees(dx_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return [round(lon + dlon, 7), round(lat + dlat, 7)]


def rectangle(
    lat: float, lon: float, width_m: float, height_m: float, dx_m: float = 0.0, dy_m: float = 0.0
) -> Polygon:
    """Rectángulo de ``width_m`` (este-oeste) × ``height_m`` (norte-sur) centrado en (lat, lon) + desplazamiento."""
    cx, cy = dx_m, dy_m
    hw, hh = width_m / 2, height_m / 2
    corners = [(cx - hw, cy - hh), (cx + hw, cy - hh), (cx + hw, cy + hh), (cx - hw, cy + hh)]
    ring = [offset(lat, lon, x, y) for x, y in corners]
    ring.append(ring[0])
    return Polygon(coordinates=[ring])
