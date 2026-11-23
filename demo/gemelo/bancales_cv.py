"""Detección automática de muros de bancal sobre la ortofoto PNOA (sin entrenamiento).

Idea:
  * El MDT del IGN (5 m) da la dirección de la ladera en cada punto → los muros deben ir
    paralelos a las curvas de nivel (perpendiculares a la pendiente).
  * En la ortofoto, el borde de cada muro/talud es una franja CLARA, fina y continua.
    Eso funciona igual con 1, 2 o más filas de árboles por bancal.
  * Filtro de cresta clara en la dirección de la pendiente (2ª derivada direccional),
    difuminado a lo largo de la curva de nivel para saltar huecos (árboles, sombras),
    supresión de no-máximos, trazado de polilíneas, unión de tramos y prolongación
    hasta el borde del terreno o hasta otro muro.
  * Los caminos que cruzan en diagonal se descartan porque no siguen las curvas de nivel.

Uso como script de prueba (genera una imagen de depuración):
    python demo/gemelo/bancales_cv.py X0 Y0 X1 Y1 salida.png      (coordenadas EPSG:25830)
"""
from __future__ import annotations

import io
import json
import math
import sys
from pathlib import Path
from urllib.request import Request, urlopen

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

PX = 0.25  # metros por píxel de la ortofoto usada para detectar
WMS = "https://www.ign.es/wms-inspire/pnoa-ma"
WCS = "https://servicios.idee.es/wcs-inspire/mdt"


# ----------------------------------------------------------------------------- descarga
def _get(url: str, tries: int = 4, timeout: float = 90) -> bytes:
    import time
    for t in range(tries):
        try:
            with urlopen(Request(url, headers={"User-Agent": "demeter-demo"}), timeout=timeout) as r:
                return r.read()
        except Exception:                                  # el IGN a veces da 502 puntuales
            if t == tries - 1:
                raise
            time.sleep(1.5 * (t + 1))


def ortho(x0, y0, x1, y1, px=PX) -> np.ndarray:
    """Ortofoto PNOA en EPSG:25830. Primero WMS; si el IGN falla (502 frecuentes), mosaico de teselas WMTS reproyectado."""
    w, h = round((x1 - x0) / px), round((y1 - y0) / px)
    url = (f"{WMS}?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=OI.OrthoimageCoverage&STYLES="
           f"&CRS=EPSG:25830&BBOX={x0},{y0},{x1},{y1}&WIDTH={w}&HEIGHT={h}&FORMAT=image/jpeg")
    try:
        return np.asarray(Image.open(io.BytesIO(_get(url, tries=1, timeout=20))).convert("RGB"), dtype=np.float32) / 255.0
    except Exception:  # noqa: BLE001
        return _ortho_wmts(x0, y0, x1, y1, w, h)


WMTS = ("https://www.ign.es/wmts/pnoa-ma?service=WMTS&request=GetTile&version=1.0.0&Format=image/jpeg"
        "&layer=OI.OrthoimageCoverage&style=default&tilematrixset=GoogleMapsCompatible&TileMatrix={z}&TileRow={y}&TileCol={x}")


def utm_to_ll(E, N, zone=30):
    """UTM (ETRS89/GRS80) → lat, lon en grados. Vectorizado."""
    a, f, k0 = 6378137.0, 1 / 298.257222101, 0.9996
    e2 = f * (2 - f); ep2 = e2 / (1 - e2)
    x = np.asarray(E, np.float64) - 500000.0; M = np.asarray(N, np.float64) / k0
    mu = M / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - np.sqrt(1 - e2)) / (1 + np.sqrt(1 - e2))
    p1 = (mu + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * np.sin(2 * mu) + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * np.sin(4 * mu)
          + (151 * e1 ** 3 / 96) * np.sin(6 * mu) + (1097 * e1 ** 4 / 512) * np.sin(8 * mu))
    s, c, t = np.sin(p1), np.cos(p1), np.tan(p1)
    C1, T1 = ep2 * c ** 2, t ** 2
    N1 = a / np.sqrt(1 - e2 * s ** 2); R1 = a * (1 - e2) / (1 - e2 * s ** 2) ** 1.5; D = x / (N1 * k0)
    lat = p1 - (N1 * t / R1) * (D ** 2 / 2 - (5 + 3 * T1 + 10 * C1 - 4 * C1 ** 2 - 9 * ep2) * D ** 4 / 24
                                 + (61 + 90 * T1 + 298 * C1 + 45 * T1 ** 2 - 252 * ep2 - 3 * C1 ** 2) * D ** 6 / 720)
    lon = (D - (1 + 2 * T1 + C1) * D ** 3 / 6 + (5 - 2 * C1 + 28 * T1 - 3 * C1 ** 2 + 8 * ep2 + 24 * T1 ** 2) * D ** 5 / 120) / c
    return np.degrees(lat), (zone * 6 - 183) + np.degrees(lon)


def _ortho_wmts(x0, y0, x1, y1, w, h, z=19):
    from concurrent.futures import ThreadPoolExecutor
    E = x0 + (np.arange(w) + .5) * (x1 - x0) / w
    N = y1 - (np.arange(h) + .5) * (y1 - y0) / h
    EE, NN = np.meshgrid(E, N)
    lat, lon = utm_to_ll(EE, NN)
    n = 2 ** z
    gx = (lon + 180) / 360 * n * 256
    gy = (1 - np.log(np.tan(np.radians(lat)) + 1 / np.cos(np.radians(lat))) / np.pi) / 2 * n * 256
    tx0, tx1 = int(gx.min() // 256), int(gx.max() // 256)
    ty0, ty1 = int(gy.min() // 256), int(gy.max() // 256)
    mosaic = np.zeros(((ty1 - ty0 + 1) * 256, (tx1 - tx0 + 1) * 256, 3), np.float32)

    def tile(t):
        tx, ty = t
        im = np.asarray(Image.open(io.BytesIO(_get(WMTS.format(z=z, x=tx, y=ty)))).convert("RGB"), np.float32) / 255
        return tx, ty, im
    tiles = [(tx, ty) for ty in range(ty0, ty1 + 1) for tx in range(tx0, tx1 + 1)]
    with ThreadPoolExecutor(8) as ex:
        for tx, ty, im in ex.map(tile, tiles):
            mosaic[(ty - ty0) * 256:(ty - ty0 + 1) * 256, (tx - tx0) * 256:(tx - tx0 + 1) * 256] = im
    rr, cc = gy - ty0 * 256 - .5, gx - tx0 * 256 - .5
    return np.stack([ndi.map_coordinates(mosaic[..., k], [rr, cc], order=1, mode="nearest") for k in range(3)], -1)


def mdt(x0, y0, x1, y1):
    x0m, y0m = math.floor(x0 / 5) * 5 - 20, math.floor(y0 / 5) * 5 - 20
    x1m, y1m = math.ceil(x1 / 5) * 5 + 20, math.ceil(y1 / 5) * 5 + 20
    url = (f"{WCS}?SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage&CoverageId=Elevacion25830_5"
           f"&SUBSET=x({x0m},{x1m})&SUBSET=y({y0m},{y1m})&FORMAT=application/asc")
    txt = _get(url).decode("latin-1")
    tok = txt[txt.index("ncols"):].split()
    hdr, i = {}, 0
    while not _isnum(tok[i]) and _isnum(tok[i + 1]):
        hdr[tok[i].lower()] = float(tok[i + 1]); i += 2
    nc, nr = int(hdr["ncols"]), int(hdr["nrows"])
    z = np.array([float(t) for t in tok[i:i + nc * nr]], dtype=np.float32).reshape(nr, nc)
    return z, hdr["xllcorner"], hdr["yllcorner"], hdr["cellsize"]


def _isnum(s: str) -> bool:
    try:
        float(s); return True
    except ValueError:
        return False


# ----------------------------------------------------------------------------- parámetros
# Valores por defecto; `params.json` (generado por ajustar.py) los sobrescribe si existe.
DEFAULTS = {
    "escalas": [1.5, 2.5, 3.5],   # σ en píxeles del filtro de cresta (0,4–0,9 m de ancho de borde)
    "k_asim": 0.0,                # peso del borde claro→oscuro ladera abajo (sombra / cara del muro)
    "blur_m": 3.0,                # difuminado a lo largo de la curva de nivel (± metros)
    "nms_m": 0.75,                # supresión de no-máximos a través de la pendiente (± metros) ≈ separación mínima
    "percentil": 82,              # umbral de respuesta (percentil dentro de la parcela)
    "min_len_m": 10.0,            # longitud mínima de un muro antes de prolongarlo
    "align_min": 0.75,            # alineación mínima con las curvas de nivel (descarta caminos en diagonal)
    "sep_min_m": 0.0,             # fusiona líneas paralelas más cercanas que esto (0 = desactivado)
    "ext_conf_min": 0.0,          # solo se prolongan los muros con confianza ≥ esto
    "ext_len_min_m": 0.0,         # … y con longitud ≥ esto
}
_PARAMS_FILE = Path(__file__).parent / "params.json"


def params_actuales(over=None):
    p = dict(DEFAULTS)
    if _PARAMS_FILE.exists():
        p.update(json.loads(_PARAMS_FILE.read_text(encoding="utf-8")).get("params", {}))
    if over:
        p.update(over)
    return p


# ----------------------------------------------------------------------------- detección
def detectar(x0, y0, x1, y1, poly=None, img=None, dem=None, debug=False, params=None):
    """Devuelve una lista de muros [{'pts': [[x, y], ...] (UTM), 'conf': 0..1}]."""
    P = params_actuales(params)
    F = caracteristicas(x0, y0, x1, y1, poly=poly, img=img, dem=dem, escalas=P["escalas"])
    res = decidir(F, P)
    if debug:
        return res, F
    return res


def caracteristicas(x0, y0, x1, y1, poly=None, img=None, dem=None, escalas=(1.5, 2.5, 3.5)):
    """Parte cara y que no depende de los umbrales: dirección de la ladera y respuestas de los filtros."""
    img = ortho(x0, y0, x1, y1) if img is None else img
    H, W = img.shape[:2]
    z, xll, yll, cs = mdt(x0, y0, x1, y1) if dem is None else dem
    cols = x0 + (np.arange(W) + .5) * PX
    rows = y1 - (np.arange(H) + .5) * PX
    mask = _poly_mask(poly, cols, rows) if poly is not None else np.ones((H, W), bool)

    # dirección de la ladera (MDT suavizado, remuestreado a la rejilla de la imagen)
    zs = ndi.gaussian_filter(z, 2.0)
    top = yll + z.shape[0] * cs
    CC, RR = np.broadcast_arrays((cols[None, :] - xll) / cs - .5, (top - rows[:, None]) / cs - .5)
    Z = ndi.map_coordinates(zs, [RR, CC], order=1, mode="nearest")
    gy, gx = np.gradient(Z)
    gn = np.hypot(gx, gy) + 1e-9
    ux, uy = gx / gn, gy / gn                 # ladera ARRIBA en píxeles (x = columna, y = fila)
    tx, ty = -uy, ux                          # a lo largo de la curva de nivel

    # luminancia normalizada localmente
    L = img @ np.array([.3, .59, .11], np.float32)
    Lc = L - ndi.gaussian_filter(L, 40)
    L = Lc / (np.sqrt(ndi.gaussian_filter(Lc ** 2, 40)) + 1e-3)

    # cresta clara a través de la pendiente (−d²L/du²), máximo entre escalas
    ridge = np.zeros_like(L)
    for s in escalas:
        Lxx = ndi.gaussian_filter(L, s, order=(0, 2)); Lyy = ndi.gaussian_filter(L, s, order=(2, 0))
        Lxy = ndi.gaussian_filter(L, s, order=(1, 1))
        Luu = ux * ux * Lxx + 2 * ux * uy * Lxy + uy * uy * Lyy
        ridge = np.maximum(ridge, np.maximum(0, -Luu) * s * s)
    # borde asimétrico: claro arriba → oscuro abajo (cara del muro / sombra)
    Lx = ndi.gaussian_filter(L, 2.0, order=(0, 1)); Ly = ndi.gaussian_filter(L, 2.0, order=(1, 0))
    asim = np.maximum(0, ux * Lx + uy * Ly)
    return {"bbox": (x0, y0, x1, y1), "img": img, "mask": mask, "ux": ux, "uy": uy, "tx": tx, "ty": ty,
            "ridge": ridge, "asim": asim, "H": H, "W": W}


def decidir(F, P):
    """Parte barata, dependiente de parámetros: combinar, umbralizar, trazar, unir, filtrar, prolongar."""
    x0, y0, x1, y1 = F["bbox"]
    H, W, mask = F["H"], F["W"], F["mask"]
    ux, uy, tx, ty = F["ux"], F["uy"], F["tx"], F["ty"]
    resp = F["ridge"] + P["k_asim"] * F["asim"]

    # difuminar a lo largo de la curva de nivel (salta huecos de árboles/sombras)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    n = max(1, int(round(P["blur_m"] / PX / 1.2)))
    acc = np.zeros_like(resp)
    for k in range(-n, n + 1):
        acc += ndi.map_coordinates(resp, [yy + ty * k * 1.2, xx + tx * k * 1.2], order=1, mode="nearest")
    S = acc / (2 * n + 1)
    S[~mask] = 0

    # supresión de no-máximos a través de la pendiente (radio = separación mínima entre muros)
    nms = np.ones_like(S, bool)
    for d in range(1, max(2, int(round(P["nms_m"] / PX))) + 1):
        for sgn in (1, -1):
            nms &= S >= ndi.map_coordinates(S, [yy + uy * d * sgn, xx + ux * d * sgn], order=1, mode="nearest")
    vals = S[mask]
    thr = max(np.percentile(vals, P["percentil"]), 1e-6) if vals.size else 1
    lines = _thin(ndi.binary_dilation(nms & (S > thr) & mask, iterations=1))

    segs = [s for s in _trace(lines) if len(s) * PX >= 1.5]
    segs = _link(segs, tx, ty, ux, uy, max_gap=7 / PX, max_lat=1.2 / PX)

    out = []
    for s in segs:
        a = np.array(s, np.float32)
        if len(a) < 2:
            continue
        length = float(np.sum(np.hypot(*np.diff(a, axis=0).T)) * PX)
        if length < P["min_len_m"]:
            continue
        d = np.diff(a, axis=0); dn = np.hypot(d[:, 0], d[:, 1]) + 1e-9
        r_i, c_i = a[:-1, 0].astype(int), a[:-1, 1].astype(int)
        align = float(np.median(np.abs(d[:, 1] / dn * tx[r_i, c_i] + d[:, 0] / dn * ty[r_i, c_i])))
        if align < P["align_min"]:
            continue
        fuerza = float(np.mean(S[a[:, 0].astype(int), a[:, 1].astype(int)]) / (thr * 3))
        out.append({"rc": a, "conf": float(min(1, .5 * min(1, fuerza) + .5 * align)), "len": length,
                    "score": fuerza * length})

    # fusionar paralelas: se queda la más fuerte; descarta las que corren pegadas a ella
    if P["sep_min_m"] > 0 and out:
        sep = max(1, int(round(P["sep_min_m"] / PX)))
        ocup = np.zeros((H, W), bool); keep = []
        for o in sorted(out, key=lambda o: -o["score"]):
            linea = np.zeros((H, W), bool); _raster(linea, o["rc"])
            if linea.any() and ocup[linea].mean() >= .6:
                continue
            keep.append(o)
            ocup |= ndi.binary_dilation(linea, iterations=sep)
        out = keep

    # prolongar extremos (solo los muros fiables) hasta el borde del terreno o hasta otro muro
    occ = np.zeros((H, W), np.int32)
    for k, o in enumerate(out, 1):
        tmp = np.zeros((H, W), bool); _raster(tmp, o["rc"]); occ[tmp] = k
    occ = ndi.maximum_filter(occ, size=5)
    for k, o in enumerate(out, 1):
        if o["conf"] >= P["ext_conf_min"] and o["len"] >= P["ext_len_min_m"]:
            o["rc"] = _extend(o["rc"], mask, occ, tx, ty, max_px=200 / PX, own_id=k)

    res = []
    for o in out:
        rc = _rdp(o["rc"], 1.5)
        res.append({"pts": [[float(x0 + (c + .5) * PX), float(y1 - (r + .5) * PX)] for r, c in rc],
                    "conf": round(o["conf"], 2)})
    return res


# ----------------------------------------------------------------------------- utilidades
def _poly_mask(poly, cols, rows):
    """Punto-en-polígono vectorizado (regla par-impar) sin dependencias extra."""
    P = np.asarray(poly, np.float64)
    X, Y = np.meshgrid(cols, rows)
    inside = np.zeros(X.shape, bool)
    for (xi, yi), (xj, yj) in zip(P, np.roll(P, 1, axis=0)):
        cond = (yi > Y) != (yj > Y)
        with np.errstate(divide="ignore", invalid="ignore"):
            xint = (xj - xi) * (Y - yi) / (yj - yi) + xi
        inside ^= cond & (X < xint)
    return inside


def _thin(b):
    """Adelgazamiento morfológico simple (Zhang-Suen) con numpy."""
    img = b.astype(np.uint8).copy()
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            P = np.pad(img, 1)
            p2, p3, p4, p5 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:]
            p6, p7, p8, p9 = P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(n.astype(int) for n in nb)
            seq = nb + [p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(int) for i in range(8))
            if step == 0:
                c = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                c = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            rm = (img == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any():
                img[rm] = 0; changed = True
    return img.astype(bool)


_NB = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _trace(sk):
    """Convierte un esqueleto en polilíneas (rompe en los cruces)."""
    sk = sk.copy()
    H, W = sk.shape
    cnt = ndi.convolve(sk.astype(int), np.ones((3, 3), int), mode="constant") - 1
    sk[(cnt > 2) & sk] = False                            # quitar cruces
    segs = []
    seen = np.zeros_like(sk)
    ys, xs = np.nonzero(sk)
    deg = (ndi.convolve(sk.astype(int), np.ones((3, 3), int), mode="constant") - 1) * sk
    order = sorted(zip(ys, xs), key=lambda p: deg[p] != 1)  # empezar por extremos
    for y, x in order:
        if seen[y, x]:
            continue
        path = [(y, x)]; seen[y, x] = True
        cy, cx = y, x
        while True:
            nxt = None
            for dy, dx in _NB:
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < H and 0 <= nx < W and sk[ny, nx] and not seen[ny, nx]:
                    nxt = (ny, nx); break
            if nxt is None:
                break
            seen[nxt] = True; path.append(nxt); cy, cx = nxt
        segs.append(path)
    return segs


def _dir(a, end):
    """Dirección unitaria (dr, dc) saliendo por un extremo, usando ~8 píxeles."""
    a = np.asarray(a, np.float32)
    k = min(8, len(a) - 1)
    v = a[-1] - a[-1 - k] if end else a[0] - a[k]
    n = np.hypot(*v) + 1e-9
    return v / n


def _link(segs, tx, ty, ux, uy, max_gap, max_lat):
    """Une tramos alineados. Extremos indexados con KD-tree, emparejado voraz en una pasada."""
    from scipy.spatial import cKDTree
    if len(segs) < 2:
        return segs
    pts, dirs = [], []
    for s in segs:                                        # extremo 2i = inicio, 2i+1 = final
        pts += [s[0], s[-1]]; dirs += [_dir(s, False), _dir(s, True)]
    pts = np.asarray(pts, np.float32); dirs = np.asarray(dirs, np.float32)
    cand = []
    for a, b in cKDTree(pts).query_pairs(max_gap):
        if a // 2 == b // 2:
            continue
        v = pts[b] - pts[a]; dist = float(np.hypot(*v))
        if dist < 1e-6:
            continue
        r, c = int(pts[a][0]), int(pts[a][1])
        lat = abs(v[0] * uy[r, c] + v[1] * ux[r, c])     # desplazamiento a través de la pendiente
        if lat > max_lat or np.dot(dirs[a], v / dist) < .6 or np.dot(dirs[b], -v / dist) < .6:
            continue
        cand.append((dist + 4 * lat, a, b))
    link = {}
    parent = list(range(len(segs)))                       # evita ciclos
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for _, a, b in sorted(cand):
        if a in link or b in link:
            continue
        ra, rb = find(a // 2), find(b // 2)
        if ra == rb:
            continue
        link[a] = b; link[b] = a; parent[ra] = rb
    out, used = [], set()
    for i in range(len(segs)):                            # cabeza de cadena = algún extremo libre
        if i in used:
            continue
        if 2 * i not in link:
            entry = 2 * i
        elif 2 * i + 1 not in link:
            entry = 2 * i + 1
        else:
            continue                                      # tramo interior: lo recorrerá su cabeza
        chain, seg = [], i
        while seg not in used:
            used.add(seg)
            s_ = segs[seg]
            chain += list(s_) if entry == 2 * seg else list(s_[::-1])
            exit_end = entry ^ 1
            if exit_end not in link:
                break
            entry = link[exit_end]; seg = entry // 2
        out.append(chain)
    return out


def _raster(occ, rc):
    for (r0, c0), (r1, c1) in zip(rc[:-1], rc[1:]):
        n = int(max(abs(r1 - r0), abs(c1 - c0))) + 1
        rr = np.linspace(r0, r1, n).round().astype(int); cc = np.linspace(c0, c1, n).round().astype(int)
        ok = (rr >= 0) & (cc >= 0) & (rr < occ.shape[0]) & (cc < occ.shape[1])
        occ[rr[ok], cc[ok]] = True


def _extend(rc, mask, occ, tx, ty, max_px, own_id=None):
    """Prolonga ambos extremos siguiendo la curva de nivel hasta el borde del terreno o hasta otro muro.
    `occ` es una imagen de ids (0 = vacío) de todos los muros, ya engordada."""
    rc = [tuple(p) for p in np.asarray(rc, np.float32)]
    H, W = mask.shape
    for end in (True, False):
        d = _dir(rc, end)
        p = np.array(rc[-1] if end else rc[0], np.float32)
        added = []
        for _ in range(int(max_px)):
            r, c = int(round(p[0])), int(round(p[1]))
            if not (0 <= r < H and 0 <= c < W):
                break
            # seguir la curva de nivel local (giro suave)
            t = np.array([ty[r, c], tx[r, c]], np.float32)
            if np.dot(t, d) < 0:
                t = -t
            d = .8 * d + .2 * t; d /= np.hypot(*d) + 1e-9
            p = p + d
            r, c = int(round(p[0])), int(round(p[1]))
            if not (0 <= r < H and 0 <= c < W) or not mask[r, c]:
                added.append(tuple(p)); break
            if occ[r, c] and occ[r, c] != own_id:
                added.append(tuple(p)); break
            added.append(tuple(p))
        rc = rc + added if end else added[::-1] + rc
    return np.array(rc, np.float32)


def _rdp(a, eps):
    a = np.asarray(a, np.float32)
    if len(a) < 3:
        return a
    s, e = a[0], a[-1]; v = e - s; n = np.hypot(*v) + 1e-9
    w = a - s
    d = np.abs(v[0] * w[:, 1] - v[1] * w[:, 0]) / n
    k = int(np.argmax(d))
    if d[k] > eps:
        return np.vstack([_rdp(a[:k + 1], eps)[:-1], _rdp(a[k:], eps)])
    return np.array([s, e])


# ----------------------------------------------------------------------------- prueba
if __name__ == "__main__":
    x0, y0, x1, y1 = map(float, sys.argv[1:5])
    out = sys.argv[5] if len(sys.argv) > 5 else "bancales_debug.png"
    res, dbg = detectar(x0, y0, x1, y1, debug=True)
    print(f"{len(res)} muros detectados")
    from PIL import ImageDraw
    im = Image.fromarray((dbg["img"] * 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    for m in res:
        xy = [((x - x0) / PX, (y1 - y) / PX) for x, y in m["pts"]]
        dr.line(xy, fill=(255, 140, 0) if m["conf"] >= .7 else (255, 235, 59), width=3)
    im.save(out)
    print("guardado", out)
