"""Fase 3: entrena el clasificador de muros (Random Forest por píxel) y ajusta el post-proceso.

Pasos:
  1. Calcula características y etiquetas de cada ejemplo del dataset.
  2. Validación «dejando uno fuera» con los ejemplos de AJUSTE: cada parcela se predice con un modelo
     entrenado con las demás → elige los parámetros del post-proceso (umbral, separación…) sin trampas.
  3. Entrena el modelo final con TODOS los de ajuste y lo guarda en modelo_rf.joblib
     (bancales_cv.detectar lo usa automáticamente).
  4. Informa: F1 por parcela en la validación, F1 en TEST (nunca vistos) e importancia de cada característica.

Uso:
    python demo/gemelo/entrenar.py
    python demo/gemelo/entrenar.py --pruebas 60
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
import modelo as md  # noqa: E402

ESPACIO_POST = {
    "umbral_prob": [0.3, 0.4, 0.5, 0.6, 0.7],
    "blur_m": [2.0, 3.0, 5.0],
    "nms_m": [1.5, 2.5, 3.5, 5.0],
    "min_len_m": [6.0, 10.0, 15.0],
    "sep_min_m": [0.0, 2.5, 3.5],
    "align_min": [0.75, 0.85],
    "ext_conf_min": [0.0, 0.5, 0.7],
}


def preparar(ej):
    m = ej["meta"]
    x0, y0, x1, y1 = m["bbox"]
    P = cv.params_actuales({"usar_modelo": False})
    F = cv.caracteristicas(x0, y0, x1, y1, poly=m["poly"], img=ej["img"], dem=ej["dem"], escalas=P["escalas"])
    X = md.caracteristicas_pixel(F)
    fino = ds.pintar_muros(ej["muros"], tuple(m["bbox"]), ej["parcela"].shape, 1)
    y = md.etiquetas(fino, ej["parcela"])
    return {"ej": ej, "F": F, "X": X, "y": y}


def entrenar_con(datos):
    rng = np.random.default_rng(0)
    Xs, ys = zip(*(md.muestrear(d["X"], d["y"], rng=rng) for d in datos))
    mod = md.nuevo_modelo()
    mod.fit(np.concatenate(Xs), np.concatenate(ys))
    return mod


def f1_con(d, prob, post):
    F = dict(d["F"], prob=prob)
    P = cv.params_actuales({"usar_modelo": False, **post})
    det = cv.decidir(F, P)
    return ev.evaluar_ejemplo(d["ej"], det)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pruebas", type=int, default=40)
    args = ap.parse_args()
    random.seed(0)
    t0 = time.time()

    todos = [ds.cargar_ejemplo(p.parent) for p in sorted(ds.DATASET.glob("*/meta.json"))]
    ajuste = [e for e in todos if e["meta"].get("split") == "ajuste"]
    test = [e for e in todos if e["meta"].get("split") == "test"]
    if len(ajuste) < 2:
        print("Hacen falta al menos 2 ejemplos de ajuste."); return
    print(f"{len(ajuste)} ejemplos de ajuste, {len(test)} de test. Calculando características…")
    D = [preparar(e) for e in ajuste]
    Dt = [preparar(e) for e in test]
    print(f"  {D[0]['X'].shape[-1]} características por píxel  ({time.time() - t0:.0f} s)")

    # --- 2) validación dejando uno fuera (probabilidades fuera de muestra)
    print("Validación dejando uno fuera…")
    probs_loo = []
    for i, d in enumerate(D):
        mod = entrenar_con([x for j, x in enumerate(D) if j != i])
        p = md.predecir(mod, d["X"], d["F"]["mask"])
        probs_loo.append(p)
        y = d["y"]; ok = y >= 0
        from sklearn.metrics import roc_auc_score
        auc = roc_auc_score(y[ok], p[ok]) if len(np.unique(y[ok])) == 2 else float("nan")
        print(f"  {d['ej']['meta']['id']}: AUC por píxel {auc:.3f}")

    # --- búsqueda del post-proceso con las probabilidades fuera de muestra
    def puntuar(post):
        return float(np.mean([f1_con(d, p, post)["f1"] for d, p in zip(D, probs_loo)]))

    mejor_post = {k: v[len(v) // 2] for k, v in ESPACIO_POST.items()}
    mejor = puntuar(mejor_post)
    print(f"Post-proceso inicial: F1 LOO = {mejor:.3f}")
    for i in range(args.pruebas):
        post = {k: random.choice(v) for k, v in ESPACIO_POST.items()}
        f = puntuar(post)
        if f > mejor:
            mejor, mejor_post = f, post
            print(f"  [{i + 1}] F1 LOO = {f:.3f}  ← mejor")
    mejora = True
    while mejora:
        mejora = False
        for k, opts in ESPACIO_POST.items():
            for v in opts:
                if v == mejor_post[k]:
                    continue
                post = dict(mejor_post, **{k: v}); f = puntuar(post)
                if f > mejor + 1e-4:
                    mejor, mejor_post, mejora = f, post, True
                    print(f"  {k}={v}: F1 LOO = {f:.3f}  ← mejor")

    filas_loo = [f1_con(d, p, mejor_post) for d, p in zip(D, probs_loo)]

    # --- 3) modelo final con todos los de ajuste
    print("Entrenando modelo final…")
    final = entrenar_con(D)
    import joblib
    imp = sorted(zip(md.NOMBRES, final.feature_importances_), key=lambda x: -x[1])

    filas_test = []
    for d in Dt:
        p = md.predecir(final, d["X"], d["F"]["mask"])
        filas_test.append(f1_con(d, p, mejor_post))

    info = {
        "post": mejor_post,
        "f1_loo_ajuste": round(mejor, 3),
        "f1_test": round(float(np.mean([f["f1"] for f in filas_test])), 3) if filas_test else None,
        "n_ajuste": len(D), "n_test": len(Dt),
        "fecha": time.strftime("%Y-%m-%d %H:%M"),
        "importancia": [[n, round(float(v), 4)] for n, v in imp],
    }
    joblib.dump({"modelo": final, "post": mejor_post, "nombres": md.NOMBRES, "info": info}, md.MODELO_PATH, compress=3)
    (Path(__file__).parent / "modelo_rf.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== RESULTADO ===")
    print("Validación dejando uno fuera (ajuste):")
    for f in filas_loo:
        print(f"  {f['id']}: F1 {f['f1']:.2f}  P {f['precision']:.2f}  E {f['exhaustividad']:.2f}  "
              f"muros {f['muros_det']}/{f['muros_reales']} (sobran {f['fp']}, faltan {f['fn']})")
    print(f"  MEDIA F1 = {mejor:.3f}")
    for f in filas_test:
        print(f"TEST {f['id']}: F1 {f['f1']:.2f}  P {f['precision']:.2f}  E {f['exhaustividad']:.2f}  "
              f"muros {f['muros_det']}/{f['muros_reales']} (sobran {f['fp']}, faltan {f['fn']})")
    print("Post-proceso:", json.dumps(mejor_post))
    print("Características más útiles:", ", ".join(f"{n} {v:.3f}" for n, v in imp[:8]))
    print(f"Guardado: {md.MODELO_PATH.name}  ({time.time() - t0:.0f} s en total)")


if __name__ == "__main__":
    main()
