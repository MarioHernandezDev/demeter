# Contrato de insights: predicción a 24 h y consejo de riego (E3, #3)

Código: `demeter/api/schemas.py` (sección *Insights*) · Ejemplos: `demeter/api/sample_data.py`
(`prediction`, `irrigation`) · Pruebas: `tests/test_api_contract.py` · Rama: `feature/insights-contrato`

Fija el **JSON exacto** que devuelve la parte de insights. Lo usan el modelo de predicción (E4),
el recomendador de riego (E5), la página de insights (E6) y los tests (E7). Hoy los endpoints
devuelven datos de ejemplo (como el resto de la API, ver [api-contrato.md](api-contrato.md)); al
implementar E4/E5 solo cambia el origen de los datos, **no la forma del JSON**.

## Endpoints

| Método y ruta | Rol mínimo | Devuelve |
|---|---|---|
| GET `/api/sensors/{sensor_id}/prediction` | lector | `SensorPrediction`: 24 puntos horarios |
| GET `/api/parcels/{parcel_id}/irrigation` | lector | `IrrigationAdvice`: qué regar y cuándo |

Errores: 401 sin token, 404 si el sensor/parcela no existe **o** (predicción) no hay datos
suficientes. No se inventa una predicción: la interfaz debe mostrar «sin datos suficientes».
Convenciones generales (fechas UTC con `Z`, litros, ids) igual que en la API.

## 1. Predicción a 24 h

```json
{
  "sensor_id": "t001",
  "type": "temperatura",
  "unit": "ºC",
  "generated_at": "2026-11-18T08:17:09Z",
  "horizon_hours": 24,
  "step_minutes": 60,
  "model": "regresion-lineal-v1",
  "trend": "falling",
  "crossing": { "type": "HIGH", "at": "2026-11-18T15:00:00Z", "value": 35.4 },
  "points": [
    { "time": "2026-11-18T09:00:00Z", "value": 22.0, "lower": 21.4, "upper": 22.6 },
    "... 23 puntos más ..."
  ]
}
```

| Campo | Regla |
|---|---|
| `points` | **Siempre 24**, uno por hora en punto, empezando en la próxima hora, en orden. |
| `value` / `lower` / `upper` | Valor esperado y banda de confianza. `lower <= value <= upper`. En sensores en `%` se recortan a 0–100. |
| `trend` | `rising`, `falling` o `stable`. Compara el último punto con el primero; es «stable» si la diferencia es menor del 5 % del rango entre umbrales (o del valor, si falta un umbral). |
| `crossing` | Primer punto previsto fuera de umbral (`LOW`/`HIGH`, mismos nombres que las alertas). **`null`** si no se espera salir, o si el sensor **ya está fuera** (esa situación la cubre la alerta activa). |
| `model` | Texto informativo del modelo usado; la interfaz no debe depender de su valor. |
| `horizon_hours`, `step_minutes` | Fijos (24 y 60) por ahora; van en la respuesta para poder cambiarlos sin romper nada. |

Pensado para pintar sobre la gráfica del sensor: la línea con `value`, el área entre `lower` y
`upper`, y una marca en `crossing.at` si existe.

## 2. Consejo de riego

```json
{
  "parcel_id": 1,
  "generated_at": "2026-11-18T08:17:09Z",
  "action": "irrigate",
  "summary": "Regar 14150 L repartidos en 2 zonas, a primera hora.",
  "total_liters": 14150.0,
  "available_l": 14150.0,
  "enough_water": true,
  "factors": {
    "soil_moisture_pct": 22.0,
    "rain_probability_pct": 35.0,
    "rain_mm_24h": 1.2,
    "tank_level_pct": 56.6
  },
  "zones": [
    {
      "zone_id": 1, "zone_name": "Aguacates norte", "liters": 8613.0,
      "start_at": "2026-11-19T05:00:00Z", "duration_min": 29,
      "reason": "Suelo al 22.0 %, por debajo de lo recomendado"
    },
    "... una entrada por zona de cultivo ..."
  ]
}
```

| `action` | Significa | `zones` | `total_liters` |
|---|---|---|---|
| `irrigate` | Regar según el reparto | una por zona de cultivo | suma de `zones[].liters` |
| `wait` | Aún no hace falta; se vuelve a mirar | `[]` | `0` |
| `skip` | No regar: se espera lluvia | `[]` | `0` |

- `summary` es una frase lista para mostrar tal cual al agricultor; en `wait`/`skip` explica el porqué.
- `enough_water` es `available_l >= total_liters`. El consejo **nunca pide más agua de la que
  hay**: si lo necesario supera lo disponible, el reparto se recorta proporcionalmente (como en el
  ejemplo, donde se necesitarían 20 700 L y solo hay 14 150 L) y el `summary` lo dice.
- `factors` son los datos que justifican el consejo, para enseñarlos al lado. Cualquiera puede
  ser `null` (p. ej. sin sensor de humedad de suelo): entonces el consejo es `wait`.
- Solo se riegan zonas de tipo `crop`. Las horas de `start_at` son UTC; la interfaz las muestra en hora local.

## 3. Cómo se calcula

### Predicción (E4, #5) · `demeter/services/forecast.py` · pruebas en `tests/test_forecast.py`

Las lecturas se agrupan en medias por hora (cada lectura cuenta en su hora en punto más cercana).
Hacen falta **al menos 3 horas distintas con datos** y que la última lectura tenga **menos de 3 h**;
si no, la API responde 404 («sin datos suficientes»). Hay dos modelos (`model` dice cuál se usó):

| Modelo | Sensores | Cómo prevé |
|---|---|---|
| `ciclo-diario-v1` | temperatura, humedad ambiente, luminosidad (con ≥ 20 h de historia) | El valor de ayer a esa misma hora, más la diferencia «hoy frente a ayer» de las últimas 3 h, que se va olvidando (se reduce a la mitad cada ~8 h). |
| `tendencia-lineal-v1` | humedad del suelo, nivel de depósito y los de ciclo diario con poca historia | Recta de mínimos cuadrados de las últimas 6 h, prolongada. |

La banda es del 80 %: `±1,28·σ·√h`, donde σ es el error del modelo sobre el pasado reciente (como
mínimo, el 2 % del rango entre umbrales) y h las horas de distancia. Los porcentajes se recortan a 0–100.

### Consejo de riego (E5, #7)

Las reglas de `sample_data.py` siguen siendo de juguete (suelo bajo + poca lluvia → regar; 2 L/m²;
caudal de 300 L/min) hasta que el recomendador (E5) defina el umbral de «hace falta regar», los
litros por m² y el caudal reales.

## 4. Relación con lo existente

- `GET /api/parcels/{id}/water` ya incluye `distribution` (reparto proporcional a la superficie).
  Es una propuesta simple; el reparto con criterio es `irrigation.zones`. Se puede retirar
  `distribution` cuando la interfaz use `irrigation`.
- `AlertType` (`LOW`/`HIGH`) se reutiliza en `crossing` para que la interfaz use los mismos colores.

## 5. Decisiones para la reunión

1. ¿Horizonte fijo de 24 h o parámetro `?horizon_h=`? (se propone fijo).
2. ¿Qué sensores se predicen? Se propone todos los activos con lecturas; la luminosidad tiene poco sentido.
3. ¿Hace falta `GET .../prediction` por parcela (todos los sensores a la vez) para la página de insights?
4. ¿El consejo de riego se guarda (histórico) o se calcula siempre al vuelo? Hoy, al vuelo.
5. Cuando el agua no alcanza: ¿recortar el reparto (propuesto) o avisar y no regar?
