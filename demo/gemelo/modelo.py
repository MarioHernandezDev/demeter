"""Fase 3: clasificador por píxel «muro / no muro» (Random Forest).

Sustituye al filtro hecho a mano (cresta clara) por una probabilidad aprendida de los ejemplos
corregidos. El resto de la cadena (supresión de no-máximos, trazado, unión, prolongación) no cambia.

Características por píxel (todas relativas a la dirección de la ladera, para que sirvan en cualquier orientación):
  * luminancia a varias escalas y textura local (punteado de copas frente a talud liso)
  * cresta CLARA y banda OSCURA a través de la pendiente, varias escalas (borde del muro, cara del talud)
  * densidad de "manchas oscuras" (copas de árboles)
  * perfil a lo largo de la ladera: cómo es la luminancia 1, 2 y 4 m más arriba y más abajo
  * color (cromaticidad, índice de verdor) y pendiente del MDT
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

PX = 0.25
MODELO_PATH = Path(__file__).parent / "modelo_rf.joblib"

NOMBRES = []


def _g(a, s, order=0):
    return ndi.gaussian_filter(a, s, order=order)


def caracteristicas_pixel(F) -> np.ndarray:
    """Devuelve un array (H, W, n_caracteristicas) float32. F viene de bancales_cv.caracteristicas()."""
    L, ux, uy, tx, ty, img = F["L"], F["ux"], F["uy"], F["tx"], F["ty"], F["img"]
    H, W = L.shape
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    feats, nombres = [], []

    def add(nombre, a):
        feats.append(a.astype(np.float32)); nombres.append(nombre)

    # luminancia y textura
    for s in (1, 3, 8):
        add(f"L_s{s}", _g(L, s))
    for s in (2, 4, 8):
        m = _g(L, s); add(f"textura_s{s}", np.sqrt(np.maximum(0, _g(L * L, s) - m * m)))

    # segunda derivada a través de la pendiente: cresta clara (−) y banda oscura (+)
    for s in (1.5, 2.5, 4, 6, 8):
        Lxx = _g(L, s, (0, 2)); Lyy = _g(L, s, (2, 0)); Lxy = _g(L, s, (1, 1))
        Luu = (ux * ux * Lxx + 2 * ux * uy * Lxy + uy * uy * Lyy) * s * s
        Ltt = (tx * tx * Lxx + 2 * tx * ty * Lxy + ty * ty * Lyy) * s * s
        add(f"clara_s{s}", np.maximum(0, -Luu))
        add(f"oscura_s{s}", np.maximum(0, Luu))
        add(f"anisotropia_s{s}", np.abs(Luu) - np.abs(Ltt))     # alta = estructura lineal a lo largo de la curva de nivel

    # primera derivada ladera arriba (signo: claro arriba / oscuro abajo)
    for s in (2, 4):
        add(f"dL_arriba_s{s}", ux * _g(L, s, (0, 1)) + uy * _g(L, s, (1, 0)))

    # copas de árboles: manchas oscuras redondas (LoG), y su densidad
    log = ndi.gaussian_laplace(L, 5) * 25
    blobs = np.maximum(0, log)
    add("copas", blobs)
    add("densidad_copas", _g(blobs, 12))

    # perfil a lo largo de la ladera (contexto): luminancia suavizada a ±1, ±2, ±4 m
    Ls = _g(L, 3)
    for d_m in (1, 2, 4):
        d = d_m / PX
        for sgn, nom in ((1, "arriba"), (-1, "abajo")):
            v = ndi.map_coordinates(Ls, [yy + uy * d * sgn, xx + ux * d * sgn], order=1, mode="nearest")
            add(f"L_{nom}_{d_m}m", v - Ls)

    # continuidad a lo largo de la curva de nivel de las dos señales principales
    for nombre in ("clara_s2.5", "oscura_s6"):
        base = feats[nombres.index(nombre)]
        acc = np.zeros_like(base)
        for k in range(-8, 9):
            acc += ndi.map_coordinates(base, [yy + ty * k * 1.5, xx + tx * k * 1.5], order=1, mode="nearest")
        add(f"{nombre}_continuo", acc / 17)

    # color
    s = img.sum(-1) + 1e-3
    r, g, b = img[..., 0] / s, img[..., 1] / s, img[..., 2] / s
    add("crom_r", _g(r, 2)); add("crom_g", _g(g, 2)); add("verdor", _g(2 * g - r - b, 2))
    add("saturacion", _g(img.max(-1) - img.min(-1), 2))

    # relieve
    add("pendiente", F["pendiente"])
    if F.get("fino"):                                   # MDT02: la señal física del muro (escalón)
        fz = F["fino"]
        for k in ("borde_sup_1m", "borde_sup_2m", "pie_1m", "pie_2m", "pendiente_fina", "residuo"):
            add(k, fz[k])
        Zs = _g(fz["Z"], 2)
        for d_m in (1, 2):
            d = d_m / PX
            arriba = ndi.map_coordinates(Zs, [yy + uy * d, xx + ux * d], order=1, mode="nearest")
            abajo = ndi.map_coordinates(Zs, [yy - uy * d, xx - ux * d], order=1, mode="nearest")
            add(f"salto_{d_m}m", arriba - abajo)        # desnivel en ±d metros a través de la ladera

    # normalizar cada característica DENTRO de la parcela (media 0, desviación 1): así el modelo no puede
    # "reconocer la parcela" por su color o su pendiente media, y tiene que aprender la forma del muro
    m = F["mask"]
    for i, a in enumerate(feats):
        v = a[m]
        if v.size:
            feats[i] = (a - v.mean()) / (v.std() + 1e-6)

    global NOMBRES
    NOMBRES = nombres
    return np.stack(feats, -1)


def etiquetas(muros_px_mask_fino, parcela):
    """1 = muro (≤ 0,5 m de la línea real), 0 = no muro (≥ 2 m), −1 = se ignora (zona de duda)."""
    d = ndi.distance_transform_edt(~muros_px_mask_fino) * PX if muros_px_mask_fino.any() else np.full(parcela.shape, 1e9)
    y = np.full(parcela.shape, -1, np.int8)
    y[(d <= 1.0) & parcela] = 1          # el dibujo a mano tiene ~±1 m de error
    y[(d >= 3.0) & parcela] = 0
    return y


def muestrear(X, y, n_pos=30000, n_neg=90000, rng=None):
    rng = rng or np.random.default_rng(0)
    pos, neg = np.flatnonzero(y.ravel() == 1), np.flatnonzero(y.ravel() == 0)
    pos = rng.choice(pos, min(n_pos, len(pos)), replace=False) if len(pos) else pos
    neg = rng.choice(neg, min(n_neg, len(neg)), replace=False) if len(neg) else neg
    idx = np.concatenate([pos, neg])
    Xf = X.reshape(-1, X.shape[-1])
    return Xf[idx], np.concatenate([np.ones(len(pos), np.int8), np.zeros(len(neg), np.int8)])


def nuevo_modelo():
    from sklearn.ensemble import RandomForestClassifier
    return RandomForestClassifier(n_estimators=120, max_depth=20, min_samples_leaf=20, max_features="sqrt",
                                  class_weight="balanced", n_jobs=-1, random_state=0)


def predecir(modelo, X, mask):
    """Probabilidad de muro por píxel (solo dentro de la parcela; fuera = 0)."""
    H, W, n = X.shape
    prob = np.zeros(H * W, np.float32)
    idx = np.flatnonzero(mask.ravel())
    Xf = X.reshape(-1, n)
    for i in range(0, len(idx), 200000):                          # por bloques para no agotar memoria
        sl = idx[i:i + 200000]
        prob[sl] = modelo.predict_proba(Xf[sl])[:, 1]
    return prob.reshape(H, W)


def cargar():
    if not MODELO_PATH.exists():
        return None
    import joblib
    return joblib.load(MODELO_PATH)
