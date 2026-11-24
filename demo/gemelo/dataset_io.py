"""Guardado de ejemplos etiquetados para entrenar y evaluar la detección de bancales.

Cada ejemplo es una carpeta `dataset/<id>/` con:
    ortho.png           recorte RGB de la ortofoto PNOA a 0,25 m/píxel
    mdt.npz             relieve IGN tal cual (z, xll, yll, cs) — lo que usa `bancales_cv.detectar`
    parcela.png         máscara del terreno dibujado (blanco = dentro)
    muros.geojson       muros CORREGIDOS por la persona (la "verdad"), EPSG:25830
    muros_auto.geojson  lo que detectó el algoritmo antes de corregir (si se usó)
    mascara.png         muros de la verdad pintados con 1 m de grosor (para entrenar)
    meta.json           bbox, polígono, cultivo, árboles por bancal, notas, fecha, split…
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import bancales_cv as cv

DATASET = Path(os.environ.get("DEMETER_DATASET", Path(__file__).parent / "dataset"))  # se puede cambiar para pruebas
PX = cv.PX
ANCHO_MASCARA_M = 1.0


def split_de(ejemplo_id: str) -> str:
    """Reparto fijo 70 % ajuste / 30 % test según el id (no cambia aunque se añadan ejemplos)."""
    return "test" if int(hashlib.sha1(ejemplo_id.encode()).hexdigest(), 16) % 10 < 3 else "ajuste"


def _geojson(muros, extra=None):
    feats = []
    for m in muros:
        props = {k: v for k, v in m.items() if k != "pts"}
        feats.append({"type": "Feature", "properties": props,
                      "geometry": {"type": "LineString", "coordinates": m["pts"]}})
    return {"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:25830"}},
            "features": feats, **(extra or {})}


def leer_muros(path: Path):
    if not path.exists():
        return None
    gj = json.loads(path.read_text(encoding="utf-8"))
    return [{"pts": f["geometry"]["coordinates"], **f.get("properties", {})} for f in gj["features"]]


def utm_a_px(pts, bbox):
    x0, _, _, y1 = bbox
    return [((x - x0) / PX, (y1 - y) / PX) for x, y in pts]


def pintar_muros(muros, bbox, shape, ancho_px):
    im = Image.new("L", (shape[1], shape[0]), 0)
    dr = ImageDraw.Draw(im)
    for m in muros:
        xy = utm_a_px(m["pts"], bbox)
        if len(xy) >= 2:
            dr.line(xy, fill=255, width=max(1, int(round(ancho_px))), joint="curve")
    return np.asarray(im) > 0


def pintar_parcela(poly, bbox, shape):
    im = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(im).polygon(utm_a_px(poly, bbox), fill=255)
    return np.asarray(im) > 0


def guardar_ejemplo(req: dict) -> dict:
    """req = {bbox, poly, muros: [{pts}], muros_auto: [{pts, conf}] | None, meta: {...}}"""
    x0, y0, x1, y1 = map(float, req["bbox"])
    poly = req["poly"]
    muros = req.get("muros") or []
    ejemplo_id = time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha1(json.dumps(poly).encode()).hexdigest()[:6]
    carpeta = DATASET / ejemplo_id
    carpeta.mkdir(parents=True, exist_ok=False)

    img = cv.ortho(x0, y0, x1, y1)
    z, xll, yll, cs = cv.mdt(x0, y0, x1, y1)
    Image.fromarray((img * 255).astype(np.uint8)).save(carpeta / "ortho.png")
    np.savez_compressed(carpeta / "mdt.npz", z=z, xll=xll, yll=yll, cs=cs)

    bbox = (x0, y0, x1, y1)
    parcela = pintar_parcela(poly, bbox, img.shape[:2])
    Image.fromarray((parcela * 255).astype(np.uint8)).save(carpeta / "parcela.png")
    mascara = pintar_muros(muros, bbox, img.shape[:2], ANCHO_MASCARA_M / PX) & parcela
    Image.fromarray((mascara * 255).astype(np.uint8)).save(carpeta / "mascara.png")

    (carpeta / "muros.geojson").write_text(json.dumps(_geojson(muros)), encoding="utf-8")
    if req.get("muros_auto") is not None:
        (carpeta / "muros_auto.geojson").write_text(json.dumps(_geojson(req["muros_auto"])), encoding="utf-8")

    meta = {
        "id": ejemplo_id,
        "fecha": time.strftime("%Y-%m-%d %H:%M:%S"),
        "bbox": [x0, y0, x1, y1],
        "poly": poly,
        "px_m": PX,
        "n_muros": len(muros),
        "n_muros_auto": None if req.get("muros_auto") is None else len(req["muros_auto"]),
        "split": split_de(ejemplo_id),
        "fuente": "Ortofoto PNOA y MDT cedidos por © Instituto Geográfico Nacional (CC BY 4.0)",
        **(req.get("meta") or {}),
    }
    (carpeta / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": ejemplo_id, "split": meta["split"], "carpeta": str(carpeta), "total": total_ejemplos()}


def total_ejemplos() -> int:
    return sum(1 for p in DATASET.glob("*/meta.json")) if DATASET.exists() else 0


def cargar_ejemplo(carpeta: Path) -> dict:
    meta = json.loads((carpeta / "meta.json").read_text(encoding="utf-8"))
    d = np.load(carpeta / "mdt.npz")
    return {
        "meta": meta,
        "img": np.asarray(Image.open(carpeta / "ortho.png").convert("RGB"), np.float32) / 255,
        "dem": (d["z"], float(d["xll"]), float(d["yll"]), float(d["cs"])),
        "parcela": np.asarray(Image.open(carpeta / "parcela.png")) > 0,
        "muros": leer_muros(carpeta / "muros.geojson") or [],
        "muros_auto": leer_muros(carpeta / "muros_auto.geojson"),
    }
