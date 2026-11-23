"""Búsqueda automática de parámetros del detector de bancales (Fase 2 del plan de mejora).

Usa SOLO los ejemplos con split = "ajuste" (los de "test" no se tocan) y maximiza la F1 media.
Las características caras (filtros) se calculan una vez por ejemplo; cada prueba solo repite la parte barata.

Uso:
    python demo/gemelo/ajustar.py                 # 40 pruebas aleatorias + refinado alrededor de la mejor
    python demo/gemelo/ajustar.py --pruebas 80
    python demo/gemelo/ajustar.py --no-guardar    # solo informa, no escribe params.json

Resultado: demo/gemelo/params.json (lo lee bancales_cv.detectar automáticamente).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import bancales_cv as cv  # noqa: E402
import dataset_io as ds  # noqa: E402
import evaluar as ev  # noqa: E402

ESPACIO = {
    "escalas": [[1.5, 2.5, 3.5], [2.5, 3.5, 5.0], [1.5, 2.5]],
    "k_asim": [0.0, 0.5, 1.0, 2.0],
    "blur_m": [2.0, 3.0, 5.0, 8.0],
    "nms_m": [0.75, 1.5, 2.5, 3.5, 5.0],
    "percentil": [80, 85, 88, 91, 94, 96],
    "min_len_m": [6.0, 10.0, 15.0, 25.0],
    "align_min": [0.75, 0.85, 0.92],
    "sep_min_m": [0.0, 1.5, 2.5, 3.5],
    "ext_conf_min": [0.0, 0.6, 0.75, 0.85],
    "ext_len_min_m": [0.0, 10.0, 20.0, 40.0],
    "k_escalon": [0.0, 0.5, 1.0, 2.0, 4.0],      # solo tiene efecto si hay MDT02 en mdt02/
}


def puntuar(ejemplos, feats, P):
    filas = []
    for ej in ejemplos:
        F = feats[(ej["meta"]["id"], tuple(P["escalas"]))]
        det = cv.decidir(F, P)
        filas.append(ev.evaluar_ejemplo(ej, det))
    return float(np.mean([f["f1"] for f in filas])), filas


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pruebas", type=int, default=40)
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--no-guardar", action="store_true")
    args = ap.parse_args()
    random.seed(args.semilla)

    ejemplos = [ds.cargar_ejemplo(p.parent) for p in sorted(ds.DATASET.glob("*/meta.json"))]
    ejemplos = [e for e in ejemplos if e["meta"].get("split") == "ajuste"]
    if not ejemplos:
        print("No hay ejemplos de ajuste."); return
    print(f"{len(ejemplos)} ejemplos de ajuste. Calculando características…")
    feats = {}
    for ej in ejemplos:
        x0, y0, x1, y1 = ej["meta"]["bbox"]
        for esc in ESPACIO["escalas"]:
            feats[(ej["meta"]["id"], tuple(esc))] = cv.caracteristicas(
                x0, y0, x1, y1, poly=ej["meta"]["poly"], img=ej["img"], dem=ej["dem"], escalas=esc)

    base = cv.params_actuales()
    if list(base["escalas"]) not in ESPACIO["escalas"]:
        ESPACIO["escalas"].append(list(base["escalas"]))
        for ej in ejemplos:
            x0, y0, x1, y1 = ej["meta"]["bbox"]
            feats[(ej["meta"]["id"], tuple(base["escalas"]))] = cv.caracteristicas(
                x0, y0, x1, y1, poly=ej["meta"]["poly"], img=ej["img"], dem=ej["dem"], escalas=base["escalas"])
    t = time.time()
    f_base, _ = puntuar(ejemplos, feats, base)
    print(f"Parámetros actuales: F1 = {f_base:.3f}  ({time.time() - t:.0f} s por prueba)")
    mejor = (f_base, dict(base))
    probados = []

    def probar(P, etiqueta):
        nonlocal mejor
        f1, _ = puntuar(ejemplos, feats, P)
        probados.append((f1, P))
        marca = ""
        if f1 > mejor[0]:
            mejor = (f1, dict(P)); marca = "  ← mejor"
        print(f"  [{etiqueta}] F1 = {f1:.3f}{marca}")

    # 1) aleatoria
    for i in range(args.pruebas):
        probar({k: random.choice(v) for k, v in ESPACIO.items()}, f"{i + 1:>3}/{args.pruebas}")
    # 2) refinado: cambiar un parámetro cada vez alrededor de la mejor
    print("Refinando alrededor de la mejor…")
    mejora = True
    while mejora:
        mejora = False
        actual = mejor[0]
        for k, opciones in ESPACIO.items():
            for v in opciones:
                if v == mejor[1][k]:
                    continue
                probar(dict(mejor[1], **{k: v}), f"{k}={v}")
        mejora = mejor[0] > actual + 1e-4

    f1, P = mejor
    _, filas = puntuar(ejemplos, feats, P)
    print(f"\nMEJOR F1 (ajuste) = {f1:.3f}  (antes {f_base:.3f})")
    for f in filas:
        print(f"  {f['id']}: F1 {f['f1']:.2f}  P {f['precision']:.2f}  E {f['exhaustividad']:.2f}  "
              f"muros {f['muros_det']}/{f['muros_reales']}")
    print(json.dumps(P, indent=2))
    if not args.no_guardar:
        (Path(__file__).parent / "params.json").write_text(json.dumps({
            "params": P, "f1_ajuste": round(f1, 3), "f1_ajuste_antes": round(f_base, 3),
            "n_ejemplos_ajuste": len(ejemplos), "fecha": time.strftime("%Y-%m-%d %H:%M"),
        }, indent=2), encoding="utf-8")
        print("Guardado en params.json — ahora ejecuta evaluar.py para ver ajuste y TEST.")


if __name__ == "__main__":
    main()
