# Dataset de bancales (Fase 1)

Ejemplos etiquetados a mano para **medir** y, más adelante, **entrenar** la detección automática de muros de bancal.
Se crean desde el editor del gemelo con **«💾 Guardar como ejemplo»**. Cada carpeta es una parcela.

> Las carpetas de ejemplos no se suben a git (pesan varios MB cada una). Para compartirlas con el equipo,
> comprime `dataset/` y pásalo por Drive. La ortofoto y el MDT son del IGN, con licencia CC BY 4.0.

## Cómo etiquetar una parcela (5–10 min)

1. Abre la zona: `http://localhost:8765/?lat=36.75&lng=-3.55&z=18`.
2. **Dibujar mi terreno** → **Generar plano** → **✨ Detectar bancales**.
3. Revisa **todos** los muros sobre la ortofoto, con zoom 19–20:
   - **Borrar muro** en los que sobran: caminos, bordes de casas, líneas dobles…
   - **Dibujar muro** en los que faltan.
   - Si un muro está desplazado más de 1 m, bórralo y dibújalo bien.
4. **💾 Guardar como ejemplo** → rellena cultivo, árboles por bancal y dificultad → marca «He revisado…» → Guardar.

## Criterio común (importante: todos igual)

| Caso | Qué hacer |
|---|---|
| ¿Dónde va la línea? | En el **borde superior del talud**: la franja clara donde termina la plataforma de arriba |
| Bancal con 2 o más filas de árboles | **Un solo muro** por bancal, no uno por fila |
| Muro tapado por un árbol | Trázalo de forma continua por donde pasaría |
| Muro que termina dentro de la parcela | Llévalo hasta el borde o hasta el muro más cercano, como en el terreno real |
| Camino entre bancales | No es muro, salvo que haya un escalón real a su lado |
| Escalón de menos de unos 0,4 m | No lo marques |
| Parcela llana o de invernadero | Guárdala **sin muros**: también es un ejemplo útil (el detector no debe inventar nada) |

## Qué se guarda en cada ejemplo

| Fichero | Contenido |
|---|---|
| `ortho.png` | Ortofoto PNOA, 0,25 m/píxel |
| `mdt.npz` | Relieve del IGN (5 m), tal cual lo usa el detector |
| `parcela.png` | Máscara del terreno dibujado |
| `muros.geojson` | Muros corregidos, la **verdad** (EPSG:25830) |
| `muros_auto.geojson` | Lo que detectó el algoritmo antes de corregir |
| `mascara.png` | Muros de la verdad pintados con 1 m de grosor, para entrenar |
| `meta.json` | Cultivo, árboles por bancal, dificultad, notas, fecha y `split` (`ajuste` o `test`) |

El `split` se asigna solo: aproximadamente un 70 % para **ajustar o entrenar** y un 30 % reservado para **test**. Los ejemplos de test no se usan nunca para ajustar parámetros.

## Medir

```powershell
python demo/gemelo/evaluar.py
```

Vuelve a ejecutar el detector actual sobre todos los ejemplos y escribe `dataset/informe/resumen.md`, junto con una imagen por ejemplo: verde = acierto, rojo = sobra, azul = falta.

```powershell
python demo/gemelo/evaluar.py --guardado
```

Esta opción mide lo que se detectó en el momento de guardar.

## Objetivo de la Fase 1: 15–20 parcelas variadas

| Tipo | Nº |
|---|---|
| Olivar, 1 fila por bancal | 3 |
| Bancales con 2 o más filas | 3 |
| Aguacate / mango (copa grande) | 3 |
| Sin árboles / recién labrado | 2 |
| Con camino o casa dentro | 2 |
| Invernadero o llano (sin muros) | 2 |
| Arbolado muy denso | 2 |
