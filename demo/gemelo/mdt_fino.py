"""Relieve fino: MDT02 (2 m, PNOA LiDAR 2ª cobertura) desde ficheros locales.

El MDT02 no se sirve por WCS: se descarga del Centro de Descargas del CNIG como GeoTIFF (COG) por
hoja MTN25 y se deja en `demo/gemelo/mdt02/`. Este módulo lee las hojas que cubran una zona y devuelve
la rejilla en el mismo formato que `bancales_cv.mdt()`: (z, xll, yll, cs).

Lectura con Pillow (sin GDAL/rasterio): usa las etiquetas GeoTIFF ModelPixelScale (33550) y
ModelTiepoint (33922). Solo EPSG:25830 (ETRS89 / UTM 30N), que es el de la zona de Motril.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

CARPETA = Path(__file__).parent / "mdt02"
Image.MAX_IMAGE_PIXELS = None


@lru_cache(maxsize=None)
def _cabecera(path: str):
    with Image.open(path) as im:
        tags = im.tag_v2
        sx, sy = tags[33550][:2]
        _, _, _, X, Y, _ = tags[33922][:6]
        w, h = im.size
        # huso: si la clave de proyección dice 25829/25831 no nos vale
        geo = tags.get(34735)
        epsg = None
        if geo:
            g = list(geo)
            for k in range(4, len(g), 4):
                if g[k] == 3072:          # ProjectedCSTypeGeoKey
                    epsg = g[k + 3]
    return {"x0": float(X), "y1": float(Y), "sx": float(sx), "sy": float(sy), "w": w, "h": h, "epsg": epsg}


@lru_cache(maxsize=8)
def _datos(path: str):
    try:
        with Image.open(path) as im:
            a = np.asarray(im, dtype=np.float32)
    except Exception:  # noqa: BLE001 — p. ej. predictor de coma flotante que Pillow no decodifica
        try:
            import tifffile
        except ImportError as e:
            raise RuntimeError(f"No se puede leer {Path(path).name} con Pillow. Instala tifffile: "
                               "pip install tifffile imagecodecs") from e
        a = tifffile.imread(path).astype(np.float32)
    a = a.copy()
    a[(a < -1000) | (a > 9000)] = np.nan          # sin dato
    return a


def hojas():
    return sorted(str(p) for p in CARPETA.glob("*.tif*")) + sorted(str(p) for p in CARPETA.glob("*.TIF")) \
        if CARPETA.exists() else []


def disponible(x0, y0, x1, y1) -> bool:
    return cargar(x0, y0, x1, y1) is not None


def cargar(x0, y0, x1, y1, margen=20.0):
    """Mosaico MDT02 que cubre la zona (con margen). None si no hay hojas o no la cubren entera."""
    x0, y0, x1, y1 = x0 - margen, y0 - margen, x1 + margen, y1 + margen
    cs = None
    trozos = []
    for p in hojas():
        try:
            c = _cabecera(p)
        except Exception:  # noqa: BLE001 — fichero que no es GeoTIFF válido
            continue
        if c["epsg"] not in (None, 25830):
            continue
        hx0, hy1 = c["x0"], c["y1"]
        hx1, hy0 = hx0 + c["w"] * c["sx"], hy1 - c["h"] * c["sy"]
        if hx1 <= x0 or hx0 >= x1 or hy1 <= y0 or hy0 >= y1:
            continue
        trozos.append((p, c)); cs = c["sx"]
    if not trozos:
        return None
    nx, ny = int(np.ceil((x1 - x0) / cs)), int(np.ceil((y1 - y0) / cs))
    z = np.full((ny, nx), np.nan, np.float32)
    for p, c in trozos:
        a = _datos(p)
        # ventana de la hoja que cae en la zona
        c0 = int(np.floor((x0 - c["x0"]) / c["sx"])); r0 = int(np.floor((c["y1"] - y1) / c["sy"]))
        for rr in range(ny):
            r = r0 + rr
            if not (0 <= r < c["h"]):
                continue
            cc0, cc1 = max(0, c0), min(c["w"], c0 + nx)
            if cc0 >= cc1:
                continue
            fila = a[r, cc0:cc1]
            destino = z[rr, cc0 - c0:cc1 - c0]
            m = np.isnan(destino)
            destino[m] = fila[m]
    if np.isnan(z).mean() > .02:                  # la zona no está cubierta del todo
        return None
    if np.isnan(z).any():                          # huecos pequeños: rellenar con el vecino
        from scipy import ndimage as ndi
        idx = ndi.distance_transform_edt(np.isnan(z), return_distances=False, return_indices=True)
        z = z[tuple(idx)]
    xll, yll = x0 + 0.0, y1 - ny * cs
    # alinear al origen de la hoja (x0 se tomó de la ventana)
    p0, c = trozos[0]
    xll = c["x0"] + int(np.floor((x0 - c["x0"]) / c["sx"])) * cs
    yll = c["y1"] - (int(np.floor((c["y1"] - y1) / c["sy"])) + ny) * cs
    return z, float(xll), float(yll), float(cs)
