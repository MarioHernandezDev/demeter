# Contrato del repositorio de datos (B6, #13)

> **Versión:** 1.0 (24/11/2026: las tres entregas implementadas; cierra la #13)
> **Código:** `demeter/db/repositorio.py` y `demeter/db/conexion.py` · **Pruebas:** `tests/test_repository.py`
> **Autor:** David
> **Tablas:** [`docs/modelo-datos.md`](modelo-datos.md) v1.1 · **API:** [`docs/api-contrato.md`](api-contrato.md)

Este documento fija **qué funciones ofrece la capa de consultas a la base de datos**, con qué
parámetros y qué devuelven. Sirve para que la API (Alex), el motor de alertas (Mario L.), la
interfaz (Nieto) y el simulador y el seed (David) escriban contra ella sin esperar al código.

El repositorio sustituye a `demeter/api/sample_data.py`: donde las rutas llaman hoy a
`d.readings(...)`, pasarán a llamar a `repo.readings(...)`.

## 1. Cómo se usa

```python
from demeter.db import repositorio as repo

repo.save_reading("t001", timestamp, 21.5)
repo.readings("t001", limit=50)
```

## 2. Reglas generales

1. **Una sesión por llamada.** Cada función abre y cierra la suya. Lo que devuelve ya está
   construido y no depende de ninguna sesión abierta. **Única excepción:** `save_reading` acepta
   la sesión de quien la llama (ver 4.1), para que la ingesta guarde la lectura y evalúe sus
   alertas en una sola transacción.
2. **Devuelve los esquemas de la API** (`s.Reading`, `s.Sensor`, `s.Alert`...), así que las rutas
   casi no cambian. **Única excepción: las consultas de usuario para el login**, que devuelven
   el modelo `User` de la base de datos porque necesitan `password_hash`, que `s.User` no lleva.
3. **Fechas siempre en UTC y con zona horaria.** La base de datos rechaza fechas sin zona. Si a
   una función le llega una fecha sin zona, la **trata como UTC**. Las que devuelve llevan zona.
   Quien cree fechas debe usar `datetime.now(timezone.utc)`, nunca `datetime.now()`.
4. **Lo que no existe no es un error en las lecturas:** una consulta de un elemento devuelve
   `None` y una de varios devuelve una lista vacía.
5. **Las escrituras sobre algo que no existe** (guardar una lectura de un sensor inexistente,
   crear una zona en una parcela inexistente) lanzan `NotFoundError`. La API debería comprobar
   antes la existencia, como hace ya con `_parcel()` y `_sensor()`.
6. **El repositorio guarda y consulta, no decide.** Las reglas (cuándo se abre una alerta, el
   estado `ok/LOW/HIGH` de un sensor, los permisos, el reparto de agua, la predicción) siguen en
   `demeter/services/` y en la API. Ahí se combinan las funciones de este documento.
7. **Dar de baja es desactivar** (decisión 24 del modelo). Nada de aquí borra parcelas, sensores
   ni usuarios. Lo único que se borra es un elemento del terreno (`delete_element`).

## 3. Diferencias con `sample_data.py`

No todas las funciones son una sustitución directa:

| `sample_data` | Repositorio | Por qué cambia |
|---|---|---|
| `readings(sensor)` recibe un objeto `Sensor`; `since` y `limit` se aplican después en Python | `readings(sensor_id, since=None, limit=100)` filtra **en SQL** | La tabla llegará a unas 600.000 filas: no se puede cargar entera para recortarla |
| `last_reading(sensor)` | `last_reading(sensor_id)` | Se pide por código, sin construir el sensor antes |
| `sensor_by_id(id)` | `get_sensor(sensor_id)` | Nombres con verbo, como el resto |
| Estado `ok/LOW/HIGH/sin_datos` calculado en `sample_data` | No está en el repositorio | Es de `alert_rules.card_status` (Mario L.) |
| `water`, `weather`, `prediction`, `irrigation` | No están en el repositorio | Se calculan a partir de lecturas y depósitos (decisión 26 del modelo) |

## 4. Funciones

### 4.1 Lecturas, parcelas y sensores (entrega 1)

| Función | Devuelve | Qué hace |
|---|---|---|
| `save_reading(sensor_id, timestamp, value, session=None)` | `s.IngestResult` | Guarda una lectura. Si ya existe una con el mismo sensor y hora, **no es un error**: devuelve `stored=False, duplicate=True`. Además actualiza `sensors.last_seen_at`, **solo si la lectura es más reciente** que la que había (una lectura atrasada se guarda pero no mueve `last_seen_at`). Un valor no finito (`NaN`, `inf`) lanza `ValueError`. **Con `session`**, trabaja dentro de esa transacción y **no hace `commit`** (sí actualiza `last_seen_at` dentro de ella): la ingesta guarda, llama a `evaluar_lectura` del motor y confirma una sola vez |
| `readings(sensor_id, since=None, limit=100)` | `list[s.Reading]` | Las últimas `limit` lecturas posteriores a `since` (exclusivo), **de la más antigua a la más reciente**. Rellena `type` y `unit` con los del sensor |
| `last_reading(sensor_id)` | `s.Reading \| None` | La lectura más reciente de un sensor |
| `last_readings(parcel_id)` | `dict[str, s.Reading]` | La última lectura de cada sensor de la parcela, en una sola consulta. Sirve para el dashboard. Los sensores sin datos no aparecen |
| `list_parcels(include_inactive=False)` | `list[s.Parcel]` | Por defecto, solo las parcelas **activas**. Con `include_inactive=True`, también las desactivadas (para que un admin pueda verlas y reactivarlas) |
| `get_parcel(parcel_id)` | `s.ParcelDetail \| None` | Una parcela con su contorno (el texto GeoJSON ya convertido a `s.Polygon`) |
| `set_boundary(parcel_id, boundary, area_m2)` | `s.ParcelDetail \| None` | Guarda el contorno dibujado y su superficie. La superficie la calcula la API (`geo.polygon_area_m2`) y el repositorio solo la guarda |
| `set_parcel_active(parcel_id, active)` | `s.Parcel \| None` | Da de baja (`False`) o reactiva (`True`) una parcela **y todos sus sensores**, en una sola transacción: o cambia todo o no cambia nada. `None` si la parcela no existe |
| `parcel_sensors(parcel_id)` | `list[s.Sensor]` | Todos los sensores de la parcela, incluidos los desactivados (llevan `is_active=False`) |
| `get_sensor(sensor_id)` | `s.Sensor \| None` | Un sensor por su código |
| `update_sensor(sensor_id, changes)` | `s.Sensor \| None` | Cambia **solo los campos que vienen en el diccionario** `changes`: `threshold_low`, `threshold_high`, `latitude`, `longitude`, `is_active`. Un valor `None` explícito deja el campo vacío. Cualquier otra clave lanza `ValueError`. La API pasa `body.model_dump(exclude_unset=True)` |

### 4.2 Alertas (entrega 2)

Abrir, cerrar y buscar la alerta activa **no está en el repositorio**: lo hace el motor de
alertas de Mario L. (`demeter/services/alerts.py`), dentro de la transacción de la ingesta. Por
eso se quitaron `open_alert`, `resolve_alert` y `get_active_alert` (decisión del 24/11/2026). El
repositorio ofrece lo que necesitan la pantalla de alertas y el estado de conexión de los sensores.

| Función | Devuelve | Qué hace |
|---|---|---|
| `list_alerts(parcel_id=None, unread_only=False, alert_type=None, sensor_id=None, active=None, limit=20, offset=0, opened_since=None)` | `tuple[list[s.Alert], int]` | Alertas, **las más recientes primero** (a igual hora, desempata el id), y el **total** que cumple los filtros sin contar la paginación (para `X-Total-Count`). `active=True` solo activas, `False` solo resueltas, `None` todas. `opened_since`: solo las abiertas en esa fecha **o después** (incluida; una fecha sin zona se toma como UTC), para «últimos 7 días». Con `limit <= 0` la página va vacía y el total es el real. `offset` negativo: `ValueError` |
| `set_acknowledged(alert_id, acknowledged)` | `s.Alert \| None` | Marca una alerta como leída o no leída. No la resuelve. `None` si no existe |
| `acknowledge_all(parcel_id)` | `int` | Marca como leídas todas las alertas sin leer de la parcela y devuelve cuántas ha marcado. Repetirla devuelve 0 |
| `sensors_last_seen()` | `list[tuple[str, datetime \| None]]` | Solo lectura. Código y `last_seen_at` de los **sensores activos de parcelas activas**, por código. `None` = nunca ha enviado datos ("esperando", no caído). Para el estado conectado / esperando / sin señal |

### 4.3 Usuarios, terreno y costes (entrega 3)

| Función | Devuelve | Qué hace |
|---|---|---|
| `get_user_by_username(username)` | `models.User \| None` | Para el login con contraseña. **Modelo de BD, con `password_hash`**. Un usuario que solo entra con Google devuelve `password_hash=None` |
| `get_user_by_email(email)` | `models.User \| None` | Para el registro y la recuperación. Pasa el correo a minúsculas antes de buscar |
| `get_user_by_google_sub(google_sub)` | `models.User \| None` | Para el login con Google. **Es la única forma de enlazar una cuenta de Google**: nunca se enlaza por correo |
| `get_user(user_id)` | `models.User \| None` | Por id. La API lo usa en cada petición para leer rol y estado |
| `list_users()` | `list[s.User]` | Todos los usuarios, sin contraseña |
| `create_user(username, email, role, password_hash=None, google_sub=None, email_verified=False)` | `s.User` | Crea un usuario. Exige `password_hash` **o** `google_sub` (si no, `ValueError`; la base de datos también lo rechaza). Guarda el `email` sin espacios y en minúsculas. Rechaza un `username` vacío o con `@` y un `role` que no sea `admin`, `tecnico` o `lector` (`ValueError`). Si `username`, `email` o `google_sub` ya existen, lanza `AlreadyExistsError`. Recibe el `password_hash` ya calculado: nunca la contraseña en claro |
| `update_user(user_id, changes)` | `s.User \| None` | Cambia `role`, `is_active`, `email_verified`, `password_hash` o `google_sub`, igual que `update_sensor`. `is_active` (cuenta habilitada) y `email_verified` (correo confirmado) son cosas distintas. `None` en `role`, `is_active` o `email_verified`: `ValueError`. No deja al usuario sin `password_hash` **y** sin `google_sub` (`ValueError`). `google_sub` de otro usuario: `AlreadyExistsError` |
| `get_terrain(parcel_id)` | `s.Terrain \| None` | Todo lo del editor 3D: parcela, zonas, elementos, sensores (también los desactivados) y depósitos. Devuelve también las parcelas de baja, como `get_parcel` |
| `create_zone(parcel_id, body, area_m2)` | `s.Zone` | Crea una zona. La API calcula `area_m2`. Parcela inexistente: `NotFoundError` |
| `create_element(parcel_id, body)` | `s.TerrainElement` | Crea un árbol, bancal o camino. Parcela inexistente: `NotFoundError` |
| `delete_element(element_id)` | `bool` | Borra un elemento. `False` si no existía |
| `tanks(parcel_id)` | `list[s.Tank]` | Depósitos, por id, con el nivel sacado de la última lectura de su sensor. Sin sensor o sin lecturas, `level_pct` y `available_l` quedan en `None` (no se sabe, que no es vacío). `available_l` se redondea a 1 decimal. El porcentaje no se recorta a 0-100 |
| `transactions(parcel_id)` | `list[s.Transaction]` | Movimientos, los más recientes primero (por fecha; a igual fecha, el último apuntado) |
| `create_transaction(parcel_id, body)` | `s.Transaction` | Crea un movimiento. Parcela inexistente: `NotFoundError` |
| `balance(parcel_id)` | `s.Balance` | Ingresos, gastos y saldo, redondeados a 2 decimales al final. `by_category` con ingresos en positivo y gastos en negativo, compensados dentro de cada categoría. Sin movimientos (o parcela inexistente): todo a 0 |

## 5. Errores

Hay dos, y se importan de `demeter.db.repositorio`:

- `NotFoundError`: una escritura apunta a algo que no existe.
- `AlreadyExistsError`: se intenta crear algo único que ya existe (`username`, `email` o `google_sub`).

## 6. Preguntas abiertas y decisiones

### Pendientes

| Para | Pregunta |
|---|---|
| Alex | Cuando `s.User` tenga `email` y `email_verified`, saldrán solos: el repositorio ya los pasa |

### Cerradas (24/11/2026)

- **Entrega 3 implementada.** El repositorio rellena `is_active` en las parcelas: la API puede
  quitar el cálculo que hacía con consultas aparte.
- **Entrega 2 ajustada al motor de alertas** (Alex; pendiente de confirmar por Mario L.): se
  quitan `open_alert`, `resolve_alert` y `get_active_alert`, que hace el motor. Se queda
  `sensors_last_seen` como solo lectura. `list_alerts` devuelve `(página, total)` y
  `acknowledge_all` devuelve cuántas marcó.
- `save_reading` admite `session` para guardar la lectura y sus alertas en una transacción.
- `save_reading` rechaza valores no finitos.
- La entrega 3 se mantiene completa: Alex necesita todas sus funciones.

### Cerradas (23/11/2026)

- **Frecuencia de lecturas: una por minuto por sensor**, con OFFLINE a los 10 minutos sin
  datos (Alex y Mario L.). Unas 20.000 lecturas al día y 600.000 en 30 días con 14 sensores.

- `get_user` y `get_user_by_username` devuelven el modelo `User` con `password_hash`.
- `create_user` se queda como está, llamada con argumentos por nombre.
- `DbUserStore` lo escribe Alex en `demeter/api/auth.py` cuando entre la entrega 3, y trata
  `password_hash=None` (usuario solo de Google) como contraseña incorrecta.
- Los esquemas de la API llevarán `email` y `email_verified`, pero **no** `google_sub`, que no
  sale por la API.
- `list_parcels` oculta las parcelas desactivadas salvo con `include_inactive=True`.
- Dar de baja o reactivar una parcela arrastra a sus sensores, en el repositorio y en una
  sola transacción (`set_parcel_active`).

Este contrato se publica antes que el código para que cada uno pueda programar contra él. Si
alguna firma no os encaja, decidlo **antes** de que se implemente.
