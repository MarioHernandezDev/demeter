# Contrato del repositorio de datos (B6, #13)

> **Versión:** 0.3 (borrador; incorpora las respuestas de Alex del 23/11/2026)
> **Código:** `demeter/db/repositorio.py` y `demeter/db/conexion.py` · **Pruebas:** `tests/test_repository.py`
> **Rama:** `feature/db-repositorio` · **Autor:** David
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
   construido y no depende de ninguna sesión abierta.
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
| `save_reading(sensor_id, timestamp, value)` | `s.IngestResult` | Guarda una lectura. Si ya existe una con el mismo sensor y hora, **no es un error**: devuelve `stored=False, duplicate=True`. Además actualiza `sensors.last_seen_at`, **solo si la lectura es más reciente** que la que había (una lectura atrasada se guarda pero no mueve `last_seen_at`) |
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

Dependen de que el esquema `Alert` tenga `OFFLINE`, `resolved_at`, `value` y `threshold` (rama
`feature/api-alert-campos` de Alex, con PR abierto). Hasta que entre en `main`, esta entrega espera.

| Función | Devuelve | Qué hace |
|---|---|---|
| `list_alerts(parcel_id=None, unread_only=False)` | `list[s.Alert]` | Alertas, **las más recientes primero**. Con `parcel_id` filtra por parcela; con `unread_only=True`, solo las no leídas |
| `set_acknowledged(alert_id, acknowledged)` | `s.Alert \| None` | Marca una alerta como leída o no leída |
| `get_active_alert(sensor_id, alert_type)` | `s.Alert \| None` | La alerta **activa** (sin `resolved_at`) de ese sensor y tipo, si hay |
| `open_alert(sensor_id, alert_type, message, opened_at, value=None, threshold=None)` | `s.Alert` | Abre una alerta. Si ya hay una activa del mismo sensor y tipo, **devuelve esa y no crea otra** (la base de datos lo impone con el índice único parcial). Así el motor puede llamarla sin comprobar antes |
| `resolve_alert(alert_id, resolved_at)` | `s.Alert \| None` | Cierra una alerta. Si ya estaba resuelta, la devuelve sin cambiarla |
| `sensors_last_seen()` | `list[tuple[str, datetime \| None]]` | Código y `last_seen_at` de los **sensores activos de parcelas activas**. Es lo que necesita la comprobación OFFLINE cada 60 s. `None` = nunca ha enviado datos (y no cuenta como caído) |

### 4.3 Usuarios, terreno y costes (entrega 3)

| Función | Devuelve | Qué hace |
|---|---|---|
| `get_user_by_username(username)` | `models.User \| None` | Para el login con contraseña. **Modelo de BD, con `password_hash`**. Un usuario que solo entra con Google devuelve `password_hash=None` |
| `get_user_by_email(email)` | `models.User \| None` | Para el registro y la recuperación. Pasa el correo a minúsculas antes de buscar |
| `get_user_by_google_sub(google_sub)` | `models.User \| None` | Para el login con Google. **Es la única forma de enlazar una cuenta de Google**: nunca se enlaza por correo |
| `get_user(user_id)` | `models.User \| None` | Por id. La API lo usa en cada petición para leer rol y estado |
| `list_users()` | `list[s.User]` | Todos los usuarios, sin contraseña |
| `create_user(username, email, role, password_hash=None, google_sub=None, email_verified=False)` | `s.User` | Crea un usuario. Exige `password_hash` **o** `google_sub` (si no, `ValueError`; la base de datos también lo rechaza). Guarda el `email` en minúsculas. Rechaza un `username` con `@` (`ValueError`). Si `username`, `email` o `google_sub` ya existen, lanza `AlreadyExistsError` |
| `update_user(user_id, changes)` | `s.User \| None` | Cambia `role`, `is_active`, `email_verified`, `password_hash` o `google_sub`, igual que `update_sensor`. `is_active` (cuenta habilitada) y `email_verified` (correo confirmado) son cosas distintas |
| `get_terrain(parcel_id)` | `s.Terrain \| None` | Todo lo del editor 3D: parcela, zonas, elementos, sensores y depósitos |
| `create_zone(parcel_id, body, area_m2)` | `s.Zone` | Crea una zona. La API calcula `area_m2` |
| `create_element(parcel_id, body)` | `s.TerrainElement` | Crea un árbol, bancal o camino |
| `delete_element(element_id)` | `bool` | Borra un elemento. `False` si no existía |
| `tanks(parcel_id)` | `list[s.Tank]` | Depósitos con el nivel sacado de la última lectura de su sensor. Sin sensor o sin lecturas, `level_pct` y `available_l` quedan en `None` |
| `transactions(parcel_id)` | `list[s.Transaction]` | Movimientos, los más recientes primero |
| `create_transaction(parcel_id, body)` | `s.Transaction` | Crea un movimiento |
| `balance(parcel_id)` | `s.Balance` | Ingresos, gastos y saldo, redondeados a 2 decimales |

## 5. Errores

Hay dos, y se importan de `demeter.db.repositorio`:

- `NotFoundError`: una escritura apunta a algo que no existe.
- `AlreadyExistsError`: se intenta crear algo único que ya existe (`username`, `email` o `google_sub`).

## 6. Preguntas abiertas y decisiones

### Pendientes

| Para | Pregunta |
|---|---|
| Mario L. | ¿Bastan las seis funciones de alertas para el motor (D2) y la comprobación OFFLINE? |
| Mario L. y Alex | Frecuencia de lecturas: 1 por minuto (OFFLINE a 10 min, unas 600.000 lecturas en 30 días) o 1 cada 5 minutos (OFFLINE a 15 min, unas 120.000). Afecta al simulador (#15) y al histórico (#16), no a este contrato |

### Cerradas (respuestas de Alex, 23/11/2026)

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
