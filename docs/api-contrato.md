# Contrato de la API (A1, #20)

Código: `demeter/api/` · Pruebas: `tests/test_api_contract.py` · Rama: `feature/api-contrato`

**Todas las rutas leen y escriben en la base de datos** (repositorio de David, #13): usuarios,
parcelas, sensores, lecturas, alertas, dashboard, terreno, costes, agua, predicción y riego. El
clima es real (Open-Meteo). Los esquemas (`schemas.py`) no cambian. Lo único que ya no existe es el
«dato de ejemplo»: sin lecturas, un sensor está en `sin_datos`, un depósito sin nivel (`null`) y la
predicción da 404; nada se inventa.

Para que la API funcione, la BD tiene que estar preparada:

```
reflex db migrate               # crea las tablas
python -m demeter.db.seed       # 3 fincas, 14 sensores y 3 usuarios (se puede repetir)
```

Si no lo está, esas rutas responden `503` diciendo qué ejecutar.

## Probarlo

```
pip install fastapi uvicorn pydantic bcrypt pyjwt
uvicorn demeter.api.app:api --reload      # http://127.0.0.1:8000/docs
```

En `/docs`: `POST /api/auth/login` con `admin` / `demo1234` → copia el `access_token` → «Authorize».
Usuarios de ejemplo: `admin`, `tecnico`, `lector` (misma contraseña). El login es real: contraseñas
con bcrypt y token JWT firmado que caduca a los 60 min (`DEMETER_JWT_MINUTES`; el secreto va en
`DEMETER_JWT_SECRET`). El token solo lleva el id: el rol y si el usuario sigue activo se leen en
cada petición, así que una baja o un cambio de rol valen al instante. Los usuarios están en la
tabla `users` (`DbUserStore` en `demeter/api/auth.py`). Se puede entrar con el **nombre de usuario
o con el correo** (un texto con `@` se toma como correo; el correo no distingue mayúsculas). Un
usuario que solo entra con Google no tiene contraseña: con contraseña siempre da 401. Ingesta: cabecera
`X-API-Key: demo-ingest-key` (variable de entorno `DEMETER_INGEST_KEY` para cambiarla).

## Convenciones

- Fechas ISO 8601 en UTC con `Z`. Un sensor envía una lectura por minuto (OFFLINE salta a los 10 min). Coordenadas lat/lon; en GeoJSON `[lon, lat]`.
- m², litros, euros. Ids de sensor en texto (`"t001"`); el resto, enteros.
- Errores: 401 sin token/credenciales, 403 sin permiso, 404 no existe, 409 conflicto con el estado
  (p. ej. editar una parcela dada de baja), 422 datos inválidos, 503 BD sin preparar.
- Dar de baja es **desactivar, no borrar**. Una parcela de baja solo la ve un admin (al resto le da
  404) y al desactivarla se desactivan todos sus sensores; al reactivarla se reactivan todos.

## Endpoints

| Método y ruta | Rol mínimo | Para qué |
|---|---|---|
| GET `/api/health` | — | Estado |
| POST `/api/auth/login` · GET `/api/auth/me` | — · cualquiera | Sesión |
| GET `/api/users` | admin | Todos los usuarios, también los de baja (con `email` y `email_verified`, nunca la contraseña) |
| POST `/api/users` | admin | Crea un usuario: `username` (sin `@`), `email`, `password` (8–72), `role`. La contraseña se guarda con bcrypt. Nombre o correo repetidos (sin mirar mayúsculas): 409 |
| PATCH `/api/users/{id}` | admin | Cambia `role` o `is_active` (baja o reactivación; no se borra). Un admin no puede quitarse a sí mismo el rol ni darse de baja (409). `null` da 422 |
| GET `/api/parcels` · `/api/parcels/{id}` | lector | Parcelas (`?include_inactive=true` solo admin) |
| PATCH `/api/parcels/{id}` | admin | Dar de baja o reactivar (`{"is_active": false}`), con todos sus sensores. **409** al reactivarla si otra parcela activa del mismo propietario ya usa su nombre |
| PUT `/api/parcels/{id}/boundary` | tecnico | Contorno dibujado (calcula m²). 409 si está de baja; 422 si el contorno no es válido o el repositorio lo rechaza (contorno y superficie van juntos, rangos) |
| GET `/api/parcels/{id}/sensors` | lector | Sensores (los de baja solo los ve admin o tecnico) |
| PATCH `/api/sensors/{id}` | tecnico (umbrales: admin) | Umbrales / colocar en el mapa / activar. Solo cambia lo enviado; `null` vacía el campo; el mínimo debe ser menor que el máximo |
| GET `/api/sensors/{id}/data?limit&since` | lector | Lecturas de la BD, de antigua a reciente (un lector no ve las de un sensor de baja) |
| GET `/api/sensors/{id}/history?range=24h\|7d\|30d` | lector | Histórico **agregado** para las gráficas: por tramo (10 min, 1 h o 6 h, alineados al reloj) mínimo, media, máximo y nº de lecturas, de antiguo a reciente, **sin los tramos vacíos** (un hueco es un hueco en los datos). Trae `summary` del rango (`min`, `avg`, `max`, `count`; `null` sin datos) y los umbrales, para enseñar «cómo fue la semana» junto a los límites. Sobre 600 000 lecturas tarda unos 45 ms |
| POST `/api/sensors/{id}/data` | `X-API-Key` | Ingesta en vivo. `timestamp` opcional (si falta, hora de llegada; si viene, entre 24 h atrás y 5 min por delante, o 422). Repetida: `stored=false, duplicate=true`. Guarda la lectura y evalúa las alertas en una sola transacción; una lectura atrasada o de un sensor de baja se guarda pero no alerta |
| POST `/api/sensors/{id}/data/batch` | `X-API-Key` | Carga de histórico: `{"readings": [{timestamp, value}, …]}`, 1 a 1000 por llamada, todo o nada, horas de 2000 en adelante. **No genera alertas**. Devuelve `received`, `stored`, `duplicates` |
| GET `/api/dashboard?parcel_id=` | lector | Desde la BD: por sensor, último valor, `status` (`ok`/`LOW`/`HIGH`/`offline`/`sin_datos`) y `recent` (últimos 20 valores); las 5 alertas más recientes (activas primero); `unread_alerts` = todas las sin leer de la parcela. `weather` es el clima real (o `null` si no se pudo obtener) y `water` sigue siendo de ejemplo hasta el endpoint de agua |
| WS `/api/ws/dashboard?parcel_id=&token=` | lector | El mismo resumen en vivo: se envía al conectar y cada vez que cambia algo (mira la BD cada 2 s). Ver «WebSocket» |
| GET `/api/alerts` | lector | Alertas, las más recientes primero. Filtros: `parcel_id`, `unread_only`, `type` (`LOW`/`HIGH`/`OFFLINE`, otro valor da 422), `sensor_id`, `active` (true activas, false resueltas), `since` (solo las abiertas desde esa fecha ISO 8601; sin zona = UTC), `limit` (1–200, por defecto 20) y `offset`. Cabecera `X-Total-Count` con el total sin paginar |
| PATCH `/api/alerts/{id}` | tecnico | Marcar vista (`{"acknowledged": true}`); no la resuelve, eso lo decide el motor |
| POST `/api/alerts/ack-all?parcel_id=` | tecnico | Marca como leídas todas las de la parcela. Devuelve `{"updated": n}` (repetir da 0); 404 si la parcela no existe |
| GET `/api/parcels/{id}/weather` | lector | Clima **real** de Open-Meteo: `current` y `forecast` de las próximas 24 h. Cuenta con la finca 3 y respeta las parcelas de baja. 503 si no hay internet ni datos guardados |
| GET `/api/parcels/{id}/water` | lector | Depósitos y agua disponible. El nivel es el último valor del sensor de cada depósito (`null` si aún no hay lecturas; no es lo mismo que vacío). `distribution` es una propuesta proporcional a los m² de cultivo; el reparto de verdad es `/irrigation` |
| GET `/api/parcels/{id}/terrain` | lector | Todo para el editor 3D: parcela con contorno, zonas, elementos, sensores (un lector no ve los de baja) y depósitos |
| POST `/api/parcels/{id}/zones` · `/elements` · DELETE `/api/elements/{id}` | tecnico | Editar terreno. La zona calcula sus m². En una parcela de baja, 409. Borrar un elemento es definitivo (lo único que se borra de verdad) |
| GET/POST `/api/parcels/{id}/transactions` · GET `.../balance` | lector · tecnico | Costes e ingresos. El importe va siempre en positivo y el signo lo da `kind`. Lista: los más recientes primero. `balance`: ingresos, gastos, saldo y saldo por categoría. En una parcela de baja, 409 al apuntar |
| GET `/api/sensors/{id}/prediction` | lector | Predicción a 24 h con las últimas 72 h de lecturas. Sin datos suficientes, 404 |
| GET `/api/parcels/{id}/irrigation` | lector | Consejo de riego con zonas, humedad del suelo, depósitos y clima reales. Sin previsión del tiempo (sin internet), el consejo es `wait`: no se riega a ciegas. El sensor de humedad debe estar colocado dentro de la zona para contar para ella |

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

## WebSocket del dashboard

`ws://<servidor>/api/ws/dashboard?parcel_id=1&token=<JWT del login>`

- El navegador no puede poner cabeceras en un WebSocket, por eso el token va en la URL.
- Cada mensaje es `{"type": "dashboard", "data": {…}}`, con `data` idéntico a `GET /api/dashboard`.
  Llega uno al conectar y otro cada vez que cambia algo (una lectura, una alerta, un estado
  `offline`…); si nada cambia, no llega nada.
- El cliente puede mandar el texto `ping` y recibe `{"type": "pong"}`.
- Se cierra con el código **1008** si el token falta o no vale, si la parcela no existe o no se
  puede ver (una de baja solo la ve un admin), y más tarde si el token caduca (60 min) o el
  usuario es dado de baja. Al caducar el token hay que volver a iniciar sesión y reconectar.
- Si la conexión se cae, el cliente reconecta y recibe el estado completo; no hay mensajes
  perdidos que recuperar. `GET /api/dashboard` sigue valiendo como alternativa por sondeo.

## Clima real (Open-Meteo)

- Sale de Open-Meteo (gratis, sin clave) con las coordenadas de la parcela, redondeadas a 2
  decimales (~1 km). No sale ningún otro dato de la parcela.
- Se guarda 10 min en memoria. Si falla la llamada y hay algo guardado de hace menos de 6 h, se
  devuelve con `stale: true`. Tras un fallo no se reintenta durante 60 s.
- Sin internet y sin nada guardado: `GET /weather` da **503** y el dashboard trae `weather: null`
  (el resto del dashboard funciona). Nunca se inventa un clima: la interfaz debe mostrar
  «clima no disponible» y, si `stale` es true, que no está actualizado.
- Cambiar de servidor (p. ej. para pruebas): variable `DEMETER_WEATHER_URL`.
