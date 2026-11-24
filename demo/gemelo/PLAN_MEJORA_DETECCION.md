# Plan de mejora: detección automática de bancales

> Gemelo digital de Demeter · Detección de muros de bancal sobre la ortofoto PNOA.
> Estado de partida: algoritmo de visión por computador **sin entrenar** (`demo/gemelo/bancales_cv.py`), con parámetros ajustados a ojo y probado en una sola ladera de Motril (59 muros, 80 bancales, unos 7 s).

---

## 0. Situación actual

**Cómo funciona hoy**
1. Se descarga la ortofoto PNOA (0,25 m/píxel) y el MDT del IGN (5 m).
2. El MDT da la dirección de la ladera, así que los muros deben ir paralelos a las curvas de nivel.
3. Un filtro de **cresta clara** (segunda derivada en la dirección de la pendiente) busca el borde de cada muro.
4. Se difumina a lo largo de la curva de nivel, se aplica supresión de no-máximos, se trazan polilíneas, se unen los tramos y se prolongan hasta el borde del terreno o hasta otro muro.
5. Se descarta lo que no sigue las curvas de nivel, como los caminos en diagonal.

**Problemas conocidos**

| Problema | Efecto | Causa probable |
|---|---|---|
| Muros dobles (dos líneas a menos de 1,5 m) | Bancales falsos de menos de 1 m de ancho | Los dos bordes del talud (arriba y abajo) dan respuesta |
| Arbolado denso con copas que se tocan | Casi no hay detección; los muros salen solo de prolongar los cercanos | El borde no se ve en la imagen |
| Caminos, casas y piscinas | Falsos positivos dentro de la parcela | Bordes claros que casualmente son paralelos a las curvas de nivel |
| Desnivel total subestimado (34,5 m frente a 54 m reales) | Bancales con altura poco realista | Altura de muro fija (1,5 m) e igual para todos |
| Umbral fijo (percentil 82) | Detecta de más en parcelas limpias y de menos en las difíciles | No se adapta a cada parcela |
| Servicio WMS del IGN inestable (errores 502) | Lentitud | Ya hay respaldo con teselas WMTS |

**Lo que no tenemos todavía:** ni **datos etiquetados** ni una **métrica**. Sin eso, cualquier mejora se juzga a ojo.

---

## Fase 1: Datos y métrica (la base de todo)

**Objetivo:** poder medir objetivamente lo bien o mal que detecta, y empezar a acumular ejemplos.

### 1.1 Botón «Guardar como ejemplo» en el editor
Cuando el usuario termina de corregir una parcela (detección + borrar los falsos + dibujar los que faltan), se guarda en `demo/gemelo/dataset/<id>/`:
- `ortho.png`: recorte RGB a 0,25 m/píxel.
- `mdt.npy`: relieve remuestreado a la misma rejilla.
- `muros.geojson`: muros **corregidos** en EPSG:25830 (la «verdad»).
- `muros_auto.geojson`: lo que detectó el algoritmo antes de corregir, para medir.
- `mascara.png`: máscara de muro de 1 m de grosor, para entrenar.
- `meta.json`: bbox, polígono, fecha, tipo de cultivo y número de árboles por bancal.

### 1.2 Script de evaluación `evaluar.py`
- **Precisión**: de los muros detectados, cuántos son reales (con 1 m de tolerancia).
- **Exhaustividad**: de los muros reales, cuántos se detectan.
- **F1**: el equilibrio entre ambas, que será la cifra principal.
- **Error de bancales**: diferencia entre el número de bancales detectados y el real.
- **Minutos de corrección estimados**: muros que hay que borrar + muros que hay que dibujar. Es la métrica que de verdad importa al agricultor.
- Genera un informe con imágenes en color: aciertos en verde, falsos positivos en rojo y muros no detectados en azul.

### 1.3 Conjunto de validación inicial
- Entre **15 y 20 parcelas** corregidas a mano, variadas:

| Tipo | Nº parcelas |
|---|---|
| Olivar en bancales, 1 fila por bancal | 3 |
| Bancales con 2 filas o más (como tu segunda captura) | 3 |
| Aguacate / mango (copa grande, densa) | 3 |
| Bancales recién labrados o sin árboles | 2 |
| Parcela con camino o casa dentro | 2 |
| Invernaderos o zona llana (no debe detectar nada) | 2 |
| Zona difícil: arbolado muy denso | 2 |

- **Separación estricta**: 70 % para ajustar y 30 % reservado para medir, que nunca se toca al ajustar.

**Entregable:** cifra de F1 de partida del algoritmo actual. Por ejemplo, «F1 = 0,72; 9 minutos de corrección por hectárea».

---

## Fase 2: Pulido del algoritmo actual (sin entrenar)

**Objetivo:** arreglar los fallos conocidos con reglas, midiendo cada cambio con `evaluar.py`.

| Mejora | Qué resuelve |
|---|---|
| **Fusionar líneas paralelas** a menos de 1,5 m, quedándose con la de mayor respuesta | Muros dobles |
| **Ancho mínimo de bancal** (1,5–2 m): si dos muros quedan más cerca, se fusionan | Bancales falsos estrechos |
| **Máscara de exclusión** de edificios, piscinas y caminos asfaltados (color, saturación, formas rectas) | Falsos positivos |
| **Umbral adaptativo** por parcela (Otsu sobre la respuesta, o porcentaje según la densidad esperada) | Exceso o falta de detección |
| **Espaciado regular**: los bancales de una ladera tienen anchos parecidos; se usa para proponer muros donde falta uno entre dos detectados | Huecos en arbolado denso |
| **Altura de cada muro según el MDT**: se reparte el desnivel real entre los muros, proporcional a su posición | Desnivel subestimado |
| **Búsqueda automática de parámetros** (escalas, umbral, distancia de unión, longitud mínima), maximizando F1 en el 70 % de ajuste | Ajuste fino objetivo |
| **Rendimiento**: el adelgazado (Zhang-Suen) es el paso más lento; se vectoriza o se sustituye | Bajar de 7 s a 2–3 s |

**Entregable:** nueva versión del algoritmo con F1 medido. Objetivo orientativo: **+10 a +15 puntos** sobre la Fase 1.

---

## Fase 3: Clasificador por píxel entrenado (Random Forest)

**Objetivo:** que el sistema **aprenda** de vuestras parcelas qué es un muro, sin necesidad de GPU ni de miles de ejemplos.

### Cómo
- Para cada píxel se calculan unas 30–40 características:
  - Respuesta de cresta **clara** y **oscura** a 3–4 escalas.
  - Alineación con las curvas de nivel.
  - Color (RGB, HSV) y un índice de verdor (vegetación frente a suelo).
  - Textura local (varianza, gradiente).
  - Pendiente y curvatura del MDT.
  - Distancia a la fila de árboles más cercana.
- **Random Forest** o **Gradient Boosting** (scikit-learn / LightGBM) entrenado con las máscaras de la Fase 1: muro frente a no muro.
- Su probabilidad **sustituye** al filtro manual (el mapa `S`). El resto de la cadena (unión, prolongación, editor) no cambia.

### Ventajas
- Se entrena en segundos en un portátil y funciona con 15–30 parcelas.
- Es interpretable: se puede ver qué características pesan más.
- El modelo ocupa unos MB y no necesita GPU.

### Datos extra recomendados en esta fase
- **Infrarrojo del PNOA** (capa IRG, gratuita): con él, el índice de vegetación (NDVI) separa copa de suelo mucho mejor. Es clave en aguacate y mango.
- **MDT02 o LiDAR del PNOA** (2 m o menos): el propio relieve marca el escalón. Es la señal más fiable donde los árboles tapan el borde.

**Entregable:** modelo `modelo_rf.joblib`, comparativa de F1 entre las Fases 2 y 3, e importancia de cada característica.

---

## Fase 4: Bucle de mejora continua (aprendizaje con el uso)

**Objetivo:** que cada corrección de un usuario mejore el modelo.

1. El modelo detecta, el agricultor corrige y la corrección se guarda como ejemplo nuevo (Fase 1.1, automático).
2. **Aprendizaje activo**: se priorizan para revisar las parcelas donde el modelo duda más (confianza media), que son las que más enseñan.
3. **Reentrenamiento periódico**, por ejemplo cada 20 ejemplos nuevos. Solo se publica el modelo nuevo si **mejora** el F1 en el conjunto de validación reservado.
4. **Versionado** de modelos (`v1`, `v2`…), con su F1 y fecha, para poder volver atrás.

**Entregable:** script `reentrenar.py` y registro de versiones. Para el pitch: una gráfica de «F1 frente a número de parcelas corregidas».

---

## Fase 5: Red neuronal de segmentación (cuando haya datos suficientes)

**Objetivo:** dar el salto de calidad en los casos difíciles: arbolado denso, bordes poco marcados y tipos de cultivo nuevos.

### Cuándo
Con **200–300 parcelas** etiquetadas, o unos **2.000 recortes** de 64×64 m con aumentos de datos.

### Cómo
- **U-Net** pequeña, con un codificador MobileNet o ResNet18 preentrenado. La entrada es RGB + infrarrojo + pendiente del MDT y la salida un mapa de probabilidad de muro.
- Alternativa: una red de detección de bordes (tipo HED/DexiNed), muy adecuada para líneas finas.
- **Aumento de datos**: rotaciones, volteos, cambios de brillo y contraste, recortes aleatorios y ortofotos de años distintos de la misma parcela.
- **Función de pérdida** para líneas finas: Dice + entropía cruzada ponderada, o una pérdida que tolere 1–2 píxeles de desplazamiento.
- **Entrenamiento** en Google Colab con GPU gratuita (1–2 horas). Se exporta a **ONNX** y se ejecuta en CPU en el servidor, o en el navegador con onnxruntime-web.
- La salida de la red alimenta la misma cadena de vectorización de siempre.

### Atajos para etiquetar más rápido
- **Pseudo-etiquetas**: las predicciones del modelo de la Fase 3 en las que confía mucho se usan como etiquetas, con revisión rápida.
- **Segment Anything (SAM 2)**: segmenta cada bancal con un clic, y de ahí salen los muros.
- **Ortofotos históricas** del PNOA (vuelos anteriores) de las mismas parcelas: más ejemplos con la misma etiqueta, porque los muros no cambian.

**Entregable:** `modelo_unet.onnx`, comparativa de F1 entre las Fases 3 y 5, y tiempo de inferencia.

---

## Resumen de fases

| Fase | Qué | Esfuerzo aprox. | Necesita datos | Mejora esperada |
|---|---|---|---|---|
| 1 | Datos + métrica | 1–2 días | 15–20 parcelas corregidas | Saber dónde estamos |
| 2 | Pulido con reglas | 2–3 días | Las mismas | +10–15 puntos de F1 |
| 3 | Random Forest | 2–3 días | 20–30 parcelas | Menos falsos positivos y muros dobles |
| 4 | Bucle continuo | 1–2 días | Crece con el uso | Mejora sostenida |
| 5 | U-Net | 1 semana | 200–300 parcelas | Casos difíciles (arbolado denso) |

**Para la hackathon:** las Fases 1, 2 y 3 son realistas y dan una historia muy sólida («el modelo aprende de las correcciones del agricultor»). La 4 se puede enseñar como prototipo. La 5 queda como trabajo futuro.

---

## Riesgos y cómo mitigarlos

| Riesgo | Mitigación |
|---|---|
| Pocos datos etiquetados | El editor genera las etiquetas solo, con pseudo-etiquetas y SAM |
| Etiquetas inconsistentes entre personas | Mini-guía de etiquetado: qué es un muro, dónde se traza (borde superior del talud) |
| Sobreajuste a Motril | Incluir parcelas de otras zonas: Almuñécar, Alpujarra, Axarquía |
| Ortofoto de un año y bancales de otro | Guardar la fecha del vuelo PNOA en cada ejemplo |
| Servicio del IGN caído en la demo | Caché local de ortofoto y MDT de las parcelas de demostración |
| Licencia de datos | PNOA, MDT y Catastro: CC BY 4.0, válidos para entrenar citando la fuente |

---

## Qué tienes que darme tú en cada fase

### Fase 1: Datos y métrica
- **Coordenadas de 15–20 parcelas** variadas, siguiendo la tabla de la sección 1.3. Basta con un punto (lat, lng) de cada una, sacado de Google Maps o del visor del IGN. Si son vuestras o de conocidos, mejor, porque sabéis cómo son de verdad.
- **Corregir esas parcelas en el editor**: detectar, borrar los muros falsos, dibujar los que faltan y pulsar «Guardar como ejemplo». Unos 5–10 minutos por parcela, entre **2 y 3 horas** en total. Se puede repartir en el equipo.
- **Un criterio común de etiquetado**: decidir juntos si el muro se traza en el borde superior del talud, en el inferior o en el centro. Yo propongo el **borde superior** (la franja clara).
- **Datos reales si los tenéis**: para alguna parcela, la altura real de algunos muros y el número de bancales. Sirve para validar las alturas.

### Fase 2: Pulido con reglas
- **Revisar el informe visual** de la evaluación (verde, rojo, azul) y decirme qué fallos te parecen más graves para el usuario. Unos 15 minutos.
- **Validar el ancho mínimo** realista de un bancal en la Costa Tropical, y si hay muros de menos de 0,5 m o de más de 3 m.
- Nada más: el resto lo hago yo.

### Fase 3: Random Forest
- **Entre 10 y 15 parcelas más** corregidas, si la Fase 2 deja algún tipo de cultivo flojo (lo veremos en el informe). Unas 1–2 horas.
- **Autorización para añadir dependencias** al proyecto: `scikit-learn` (o `lightgbm`) y `joblib`.
- **Decidir si usamos el infrarrojo del PNOA** (gratuito; solo hace falta confirmarlo) y si **descargamos el MDT02** de las hojas de Motril y alrededores. Son unos cientos de MB, y los descargaría con tu permiso.

### Fase 4: Bucle continuo
- **Decidir dónde se guardan los ejemplos** en la app real: carpeta local, la base de datos de Demeter o almacenamiento en la nube. Esto lo debería decidir el equipo, con David para la base de datos y Alex para la API.
- **Aceptación del usuario**: un aviso en la app del tipo «tus correcciones ayudan a mejorar el detector» y su consentimiento, para que el pitch lo cuente bien.
- **Cada cuánto se reentrena** (por ejemplo cada 20 ejemplos) y quién aprueba publicar un modelo nuevo.

### Fase 5: U-Net (futuro)
- **Unas 200–300 parcelas etiquetadas**: lo más realista es acumularlas con el bucle de la Fase 4, o con una tarde de etiquetado en equipo usando SAM.
- **Una cuenta de Google Colab** (gratuita vale; Colab Pro acelera) o un equipo con GPU NVIDIA para entrenar.
- **Decidir dónde se ejecuta** el modelo: en el servidor (más simple) o en el navegador (sin servidor, pero más pesado para el usuario).

---

### Siguiente paso propuesto
Empezar por la **Fase 1**: implemento el botón «Guardar como ejemplo» y `evaluar.py`, y tú me pasas las coordenadas de las primeras 15–20 parcelas.
