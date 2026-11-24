"""Evalúa la detección automática de bancales contra los ejemplos corregidos a mano.

Uso:
    python demo/gemelo/evaluar.py                  # vuelve a ejecutar el detector ACTUAL sobre cada ejemplo
    python demo/gemelo/evaluar.py --guardado       # evalúa lo que se detectó al guardar (muros_auto.geojson)
    python demo/gemelo/evaluar.py --split test     # solo el 30 % reservado (no usarlo para ajustar)

Métricas (tolerancia de 1 m):
    precisión       de lo detectado, qué fracción está a ≤ 1 m de un muro real
    exhaustividad   de los muros reales, qué fracción tiene un muro detectado a ≤ 1 m
    F1              media armónica de las dos (la cifra principal)
    muros FP / FN   muros detectados que sobran / muros reales que faltan (por muro, no por píxel)
    bancales        nº de bancales resultantes, detectados frente a reales
    min. corrección estimación del tiempo de corregir a mano: 0,15 min por muro que borrar + 0,5 min por muro que dibujar

Salida: tabla por pantalla + dataset/informe/resumen.md, resumen.csv y una imagen por ejemplo
        (verde = acierto, rojo = sobra, azul = falta).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).parent))
import bancales_cv as cv  # noqa: E402
import dataset_io as ds  # noqa: E402

TOL_M = 1.0
MIN_BANCAL_M2 = 3.0
MIN_TP_FRAC = 0.7     # un muro detectado cuenta como acierto si ≥ 70 % de su longitud está a ≤ 1 m de uno real
MIN_FOUND_FRAC = 0.6  # un muro real cuenta como encontrado si ≥ 60 % de su longitud está cubierta
MIN_BORRAR, MIN_DIBUJAR = 0.15, 0.5


def _linea(m, bbox, shape):
    return ds.pintar_muros([m], bbox, shape, 1)


def _n_bancales(muros, bbox, parcela):
    barrera = ds.pintar_muros(muros, bbox, parcela.shape, 3) if muros else np.zeros_like(parcela)
    lab, n = ndi.label(parcela & ~barrera)
    if n == 0:
        return 0
    tam = np.bincount(lab.ravel())[1:] * cv.PX ** 2
    return int((tam >= MIN_BANCAL_M2).sum())


def evaluar_ejemplo(ej, detectados):
    meta, parcela = ej["meta"], ej["parcela"]
    bbox, shape = tuple(meta["bbox"]), parcela.shape
    tol_px = TOL_M / cv.PX
    real = ds.pintar_muros(ej["muros"], bbox, shape, 1) & parcela
    det = ds.pintar_muros(detectados, bbox, shape, 1) & parcela
    d_real = ndi.distance_transform_edt(~real) if real.any() else np.full(shape, np.inf)
    d_det = ndi.distance_transform_edt(~det) if det.any() else np.full(shape, np.inf)

    precision = float((d_real[det] <= tol_px).mean()) if det.any() else (1.0 if not real.any() else 0.0)
    exhaustividad = float((d_det[real] <= tol_px).mean()) if real.any() else 1.0
    f1 = 0.0 if precision + exhaustividad == 0 else 2 * precision * exhaustividad / (precision + exhaustividad)

    fp = 0
    for m in detectados:
        p = _linea(m, bbox, shape) & parcela
        if p.any() and (d_real[p] <= tol_px).mean() < MIN_TP_FRAC:
            fp += 1
    fn = 0
    for m in ej["muros"]:
        p = _linea(m, bbox, shape) & parcela
        if p.any() and (d_det[p] <= tol_px).mean() < MIN_FOUND_FRAC:
            fn += 1

    area_ha = parcela.sum() * cv.PX ** 2 / 1e4
    minutos = fp * MIN_BORRAR + fn * MIN_DIBUJAR
    return {
        "id": meta["id"], "split": meta.get("split", "?"), "cultivo": meta.get("cultivo", ""),
        "arboles": meta.get("arboles_por_bancal", ""), "ha": round(area_ha, 2),
        "precision": precision, "exhaustividad": exhaustividad, "f1": f1,
        "muros_reales": len(ej["muros"]), "muros_det": len(detectados), "fp": fp, "fn": fn,
        "bancales_reales": _n_bancales(ej["muros"], bbox, parcela),
        "bancales_det": _n_bancales(detectados, bbox, parcela),
        "min_correccion": round(minutos, 1), "min_por_ha": round(minutos / area_ha, 1) if area_ha else 0,
        "_real": real, "_det": det, "_d_real": d_real, "_d_det": d_det,
    }


def imagen_informe(ej, r, destino: Path):
    img = (ej["img"] * 255).astype(np.float32)
    img = np.where(ej["parcela"][..., None], img, img * 0.45 + 140)        # fuera del terreno, más pálido
    tol = TOL_M / cv.PX
    grueso = lambda b: ndi.binary_dilation(b, iterations=2)  # noqa: E731
    acierto = r["_det"] & (r["_d_real"] <= tol)
    sobra = r["_det"] & (r["_d_real"] > tol)
    falta = r["_real"] & (r["_d_det"] > tol)
    out = img.copy()
    out[grueso(falta)] = (40, 120, 255)
    out[grueso(sobra)] = (255, 50, 50)
    out[grueso(acierto)] = (60, 220, 60)
    Image.fromarray(out.clip(0, 255).astype(np.uint8)).save(destino)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--guardado", action="store_true", help="evaluar muros_auto.geojson en vez de re-detectar")
    ap.add_argument("--split", choices=["ajuste", "test", "todo"], default="todo")
    ap.add_argument("--sin-imagenes", action="store_true")
    args = ap.parse_args()

    carpetas = sorted(p.parent for p in ds.DATASET.glob("*/meta.json"))
    if not carpetas:
        print(f"No hay ejemplos en {ds.DATASET}. Guarda alguno desde el editor («Guardar como ejemplo»).")
        return
    informe = ds.DATASET / "informe"
    informe.mkdir(exist_ok=True)

    filas = []
    for c in carpetas:
        ej = ds.cargar_ejemplo(c)
        if args.split != "todo" and ej["meta"].get("split") != args.split:
            continue
        t = time.time()
        if args.guardado:
            if ej["muros_auto"] is None:
                print(f"  {c.name}: sin muros_auto guardados, se omite"); continue
            detectados = ej["muros_auto"]
        else:
            x0, y0, x1, y1 = ej["meta"]["bbox"]
            detectados = cv.detectar(x0, y0, x1, y1, poly=ej["meta"]["poly"], img=ej["img"], dem=ej["dem"])
        r = evaluar_ejemplo(ej, detectados)
        r["segundos"] = round(time.time() - t, 1)
        if not args.sin_imagenes:
            imagen_informe(ej, r, informe / f"{c.name}.png")
        filas.append(r)
        print(f"  {c.name} [{r['split']:6}] F1={r['f1']:.2f}  P={r['precision']:.2f}  E={r['exhaustividad']:.2f}  "
              f"muros {r['muros_det']}/{r['muros_reales']} (sobran {r['fp']}, faltan {r['fn']})  "
              f"bancales {r['bancales_det']}/{r['bancales_reales']}  ~{r['min_correccion']} min")

    if not filas:
        print("Ningún ejemplo en ese split."); return

    def media(k, fs):
        return float(np.mean([f[k] for f in fs]))

    grupos = {"todo": filas, **{s: [f for f in filas if f["split"] == s] for s in ("ajuste", "test")}}
    lineas = [f"# Evaluación de la detección de bancales\n",
              f"_{time.strftime('%Y-%m-%d %H:%M')} · {'muros guardados' if args.guardado else 'detector actual'} · tolerancia {TOL_M} m_\n",
              "| Conjunto | Ejemplos | F1 | Precisión | Exhaustividad | Muros que sobran | Muros que faltan | Min. corrección / ha |",
              "|---|---|---|---|---|---|---|---|"]
    for nombre, fs in grupos.items():
        if fs:
            lineas.append(f"| {nombre} | {len(fs)} | {media('f1', fs):.2f} | {media('precision', fs):.2f} | "
                          f"{media('exhaustividad', fs):.2f} | {sum(f['fp'] for f in fs)} | {sum(f['fn'] for f in fs)} | "
                          f"{media('min_por_ha', fs):.1f} |")
    lineas += ["", "## Por ejemplo", "",
               "| Ejemplo | Split | Cultivo | Árboles/bancal | ha | F1 | P | E | Muros det/real | Sobran | Faltan | Bancales det/real | Min |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        lineas.append(f"| [{f['id']}]({f['id']}.png) | {f['split']} | {f['cultivo']} | {f['arboles']} | {f['ha']} | "
                      f"{f['f1']:.2f} | {f['precision']:.2f} | {f['exhaustividad']:.2f} | {f['muros_det']}/{f['muros_reales']} | "
                      f"{f['fp']} | {f['fn']} | {f['bancales_det']}/{f['bancales_reales']} | {f['min_correccion']} |")
    lineas += ["", "Imágenes: verde = acierto · rojo = sobra (falso positivo) · azul = falta (no detectado)."]
    (informe / "resumen.md").write_text("\n".join(lineas), encoding="utf-8")

    campos = [k for k in filas[0] if not k.startswith("_")]
    with open(informe / "resumen.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos); w.writeheader()
        for f in filas:
            w.writerow({k: f[k] for k in campos})

    print()
    for nombre, fs in grupos.items():
        if fs:
            print(f"{nombre:7} ({len(fs)} ej.): F1 {media('f1', fs):.2f} · precisión {media('precision', fs):.2f} · "
                  f"exhaustividad {media('exhaustividad', fs):.2f} · {media('min_por_ha', fs):.1f} min/ha de corrección")
    print(f"\nInforme: {informe / 'resumen.md'}")


if __name__ == "__main__":
    main()
