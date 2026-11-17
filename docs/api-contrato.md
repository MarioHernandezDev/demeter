# Contrato de la API (A1, #20)

Código: `demeter/api/` · Pruebas: `tests/test_api_contract.py` · Rama: `feature/api-contrato`

Ahora mismo **todas las respuestas son datos de ejemplo** (finca ficticia en Carchuna, Motril):
nada se guarda. Sirve para que Interfaz y Simulador avancen. Cuando exista la BD (B1/B6) se
sustituye cada llamada a `sample_data.py` por su consulta; los esquemas (`schemas.py`) no cambian.

## Probarlo

```
pip install fastapi uvicorn pydantic
uvicorn demeter.api.app:api --reload      # http://127.0.0.1:8000/docs
```

En `/docs`: `POST /api/auth/login` con `admin` / `demo1234` → copia el `access_token` → «Authorize».
Usuarios de ejemplo: `admin`, `tecnico`, `lector` (misma contraseña). Ingesta: cabecera
`X-API-Key: demo-ingest-key` (variable de entorno `DEMETER_INGEST_KEY` para cambiarla).

## Convenciones

- Fechas ISO 8601 en UTC con `Z`. Un sensor envía una lectura por minuto (OFFLINE salta a los 10 min). Coordenadas lat/lon; en GeoJSON `[lon, lat]`.
- m², litros, euros. Ids de sensor en texto (`"t001"`); el resto, enteros.
- Errores: 401 sin token/credenciales, 403 sin permiso, 404 no existe, 422 datos inválidos.

## Endpoints

| Método y ruta | Rol mínimo | Para qué |
|---|---|---|
| GET `/api/health` | — | Estado |
| POST `/api/auth/login` · GET `/api/auth/me` | — · cualquiera | Sesión |
| GET/POST `/api/users` · PATCH `/api/users/{id}` | admin | Gestión de usuarios |
| GET `/api/parcels` · `/api/parcels/{id}` | lector | Parcelas |
| PUT `/api/parcels/{id}/boundary` | tecnico | Contorno dibujado (calcula m²) |
| GET `/api/parcels/{id}/sensors` | lector | Sensores |
| PATCH `/api/sensors/{id}` | tecnico (umbrales: admin) | Umbrales / colocar en el mapa |
| GET `/api/sensors/{id}/data?limit&since` | lector | Lecturas |
| POST `/api/sensors/{id}/data` | `X-API-Key` | Ingesta del simulador (duplicados se ignoran) |
| GET `/api/dashboard?parcel_id=` | lector | Último valor por sensor + alertas + clima + agua |
| GET `/api/alerts` · PATCH `/api/alerts/{id}` | lector · tecnico | Alertas / marcar vista |
| GET `/api/parcels/{id}/weather` · `/water` | lector | Clima y agua disponible |
| GET `/api/parcels/{id}/terrain` | lector | Todo para el editor 3D |
| POST `/api/parcels/{id}/zones` · `/elements` · DELETE `/api/elements/{id}` | tecnico | Editar terreno |
| GET/POST `/api/parcels/{id}/transactions` · GET `.../balance` | lector · tecnico | Costes e ingresos |

## Qué es nuevo respecto a `demeter/state/types.py`

Todo lo existente mantiene nombre y forma. Añadidos (la interfaz actual los ignora sin romperse):
`DashboardSummary.weather/water/unread_alerts`, alertas `OFFLINE` con `resolved_at`, `value` y `threshold`, `Sensor.latitude/longitude/is_active`,
sensor de tipo `nivel_deposito`, rol `lector`, y modelos nuevos de terreno, agua, clima y costes.

## Diferencias con el modelo de datos de David (v0.2) — a decidir

1. **Ids de sensor**: texto (`"t001"`, formato del reto) vs entero.
2. **Tipos de sensor**: en español (`temperatura`…) vs inglés.
3. **Usuarios**: `username` (Nieto/reto) vs `email`.
4. **Roles**: contrato con `admin/tecnico/lector`; el README de pantallas solo habla de admin/tecnico.
5. **Alertas**: el contrato añade `acknowledged` (para PATCH); `message` se genera al crear la alerta.
6. **Depósitos**: sensor `nivel_deposito` en %; litros = nivel % × capacidad.
7. **Umbrales**: ¿solo admin los edita? (el contrato lo asume así).
8. **Reflex**: falta enganchar con `api_transformer` cuando Mario H. suba el esqueleto.
