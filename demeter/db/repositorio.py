"""Repositorio de datos (B6, issue #13): las consultas a la base de datos que usan la API, el
motor de alertas, el simulador y la interfaz.

El contrato (qué funciones hay, qué reciben y qué devuelven) está en
``docs/repositorio-contrato.md``. Reglas que se cumplen en TODAS las funciones:

- Cada función abre su propia sesión y la cierra al terminar: quien la llama no gestiona nada.
  Única excepción: ``save_reading`` admite la sesión de quien la llama, para que la ingesta
  guarde la lectura y evalúe sus alertas en una sola transacción.
- Devuelven los esquemas de la API (``demeter.api.schemas``), nunca las filas de la base de
  datos, así que lo devuelto sigue siendo válido cuando la sesión ya está cerrada.
- Una consulta de algo que no existe devuelve ``None`` (o una lista vacía), no un error.
"""

import math
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import Session, select

from demeter.api import schemas as s
from demeter.db import conexion
from demeter.models import Alert, Parcel, Sensor, SensorData, User

# ---------------------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------------------


class NotFoundError(Exception):
    """Una escritura apunta a algo que no existe (p. ej. una lectura de un sensor inexistente)."""


class AlreadyExistsError(Exception):
    """Se intenta crear algo único que ya existe (``username``, ``email`` o ``google_sub``)."""


# ---------------------------------------------------------------------------------------
# Fechas
#
# Contrato (regla 3): las fechas son UTC y con zona horaria. De la parte difícil se encarga
# SQLModel: al guardar convierte cualquier fecha con zona a UTC (10:00+02:00 -> 08:00) y al leer
# devuelve la fecha ya en UTC con zona. Pero RECHAZA las fechas sin zona (ValueError), y el
# contrato dice que una fecha sin zona se da por UTC. Esa es la única conversión que falta y
# vive aquí, para aplicarla igual en todas las funciones.
# ---------------------------------------------------------------------------------------


def _as_utc(value: datetime) -> datetime:
    """Una fecha sin zona se toma como UTC; una con zona se deja como está."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


# ---------------------------------------------------------------------------------------
# Conversión de fila de la base de datos a esquema de la API
#
# Son cosas parecidas pero no iguales: la tabla ``parcels`` guarda el contorno como TEXTO
# (SQLite no tiene tipo JSON) y la API lo quiere como ``Polygon``; la tabla ``sensors`` tiene
# ``last_seen_at``, que la API no enseña. Convertir en un único sitio evita repetirlo en cada
# función y que dos funciones devuelvan el mismo objeto con formas distintas.
# ---------------------------------------------------------------------------------------


def _sensor(row: Sensor) -> s.Sensor:
    return s.Sensor(
        id=row.id,
        parcel_id=row.parcel_id,
        type=row.type,
        unit=row.unit,
        description=row.description,
        threshold_low=row.threshold_low,
        threshold_high=row.threshold_high,
        latitude=row.latitude,
        longitude=row.longitude,
        is_active=row.is_active,
    )


def _reading(row: SensorData, sensor: Sensor) -> s.Reading:
    # ``type`` y ``unit`` no están en la tabla de lecturas: salen del sensor (así no se repiten
    # en cada una de las ~600.000 filas).
    return s.Reading(
        sensor_id=row.sensor_id,
        timestamp=row.recorded_at,
        value=row.value,
        type=sensor.type,
        unit=sensor.unit,
    )


def _alert(row: Alert) -> s.Alert:
    # La tabla lo llama ``opened_at`` y la API ``timestamp``: se traduce aquí, en un solo sitio.
    return s.Alert(
        id=row.id,
        sensor_id=row.sensor_id,
        timestamp=row.opened_at,
        type=row.type,
        message=row.message,
        acknowledged=row.acknowledged,
        resolved_at=row.resolved_at,
        value=row.value,
        threshold=row.threshold,
    )


def _parcel(row: Parcel) -> s.Parcel:
    return s.Parcel(
        id=row.id,
        name=row.name,
        location=row.location,
        crop=row.crop,
        latitude=row.latitude,
        longitude=row.longitude,
        area_m2=row.area_m2,
        is_active=row.is_active,
    )


def _parcel_detail(row: Parcel) -> s.ParcelDetail:
    # El contorno se guarda como texto GeoJSON; aquí se convierte en ``Polygon``.
    boundary = s.Polygon.model_validate_json(row.boundary) if row.boundary else None
    return s.ParcelDetail(**_parcel(row).model_dump(), boundary=boundary)


# ---------------------------------------------------------------------------------------
# Sensores
# ---------------------------------------------------------------------------------------


def get_sensor(sensor_id: str) -> s.Sensor | None:
    """Un sensor por su código (``"t001"``). Devuelve también los desactivados."""
    with conexion.open_session() as session:
        row = session.get(Sensor, sensor_id)
        return _sensor(row) if row else None


# Los únicos campos de un sensor que se pueden cambiar con ``update_sensor``. Lo demás (código,
# parcela, tipo, unidad, ``last_seen_at``) no se edita: cambiar el tipo de un sensor dejaría sus
# lecturas con una unidad equivocada, y ``last_seen_at`` solo lo mueve ``save_reading``.
_SENSOR_EDITABLE = {"threshold_low", "threshold_high", "latitude", "longitude", "is_active"}


def update_sensor(sensor_id: str, changes: dict) -> s.Sensor | None:
    """Cambia SOLO los campos que vienen en ``changes``; el resto no se toca.

    La API le pasa ``body.model_dump(exclude_unset=True)``: un campo ausente significa "no lo
    cambies" y un campo con ``None`` significa "déjalo vacío" (p. ej. quitar un umbral). Por eso
    es un diccionario y no argumentos con valor por defecto: así se distingue lo uno de lo otro.

    - Una clave que no sea editable lanza ``ValueError`` y no se cambia NADA, ni siquiera los
      campos válidos que vinieran con ella.
    - ``is_active`` no admite ``None`` (es sí o no): lanza ``ValueError``.
    - Devuelve el sensor ya actualizado, o ``None`` si no existe.
    """
    unknown = set(changes) - _SENSOR_EDITABLE
    if unknown:
        raise ValueError(f"Campos no editables en un sensor: {sorted(unknown)}")
    if "is_active" in changes and changes["is_active"] is None:
        raise ValueError("is_active no puede ser None")
    with conexion.open_session() as session:
        row = session.get(Sensor, sensor_id)
        if row is None:
            return None
        for field, value in changes.items():
            setattr(row, field, value)
        session.commit()
        return _sensor(row)


def parcel_sensors(parcel_id: int) -> list[s.Sensor]:
    """Todos los sensores de la parcela, incluidos los desactivados (``is_active=False``).

    Si la parcela no existe o no tiene sensores, devuelve una lista vacía.
    """
    with conexion.open_session() as session:
        rows = session.exec(
            select(Sensor).where(Sensor.parcel_id == parcel_id).order_by(Sensor.id)
        ).all()
        return [_sensor(row) for row in rows]


# ---------------------------------------------------------------------------------------
# Parcelas
# ---------------------------------------------------------------------------------------


def list_parcels(include_inactive: bool = False) -> list[s.Parcel]:
    """Las parcelas, por orden de ``id``.

    Por defecto solo las activas. Con ``include_inactive=True`` también las dadas de baja, para
    que un administrador pueda verlas y reactivarlas.
    """
    with conexion.open_session() as session:
        query = select(Parcel).order_by(Parcel.id)
        if not include_inactive:
            query = query.where(Parcel.is_active)
        return [_parcel(row) for row in session.exec(query).all()]


def get_parcel(parcel_id: int) -> s.ParcelDetail | None:
    """Una parcela con su contorno. Devuelve también las dadas de baja.

    No filtra por ``is_active``: pedir una parcela concreta por su id es una petición explícita
    (el administrador que va a reactivarla, por ejemplo). Quien quiera ocultar las dadas de
    baja usa ``list_parcels``.
    """
    with conexion.open_session() as session:
        row = session.get(Parcel, parcel_id)
        return _parcel_detail(row) if row else None


# ---------------------------------------------------------------------------------------
# Lecturas
# ---------------------------------------------------------------------------------------


def save_reading(
    sensor_id: str, timestamp: datetime, value: float, session: Session | None = None
) -> s.IngestResult:
    """Guarda una lectura. Una repetida (mismo sensor y misma hora) NO es un error.

    - Sensor inexistente: ``NotFoundError``.
    - Lectura repetida: no se guarda otra y devuelve ``stored=False, duplicate=True``. Los
      sensores reintentan cuando no reciben respuesta, así que repetir es normal.
    - ``sensors.last_seen_at`` solo AVANZA: una lectura atrasada se guarda, pero no lo mueve
      hacia atrás (si no, un reenvío de datos viejos haría parecer caído un sensor que funciona).
    - Un valor no finito (``NaN``, ``inf``, ``-inf``) lanza ``ValueError`` y no se guarda nada.

    ``session`` (opcional): sin ella, la función abre su sesión y confirma (``commit``) al
    terminar. Con ella, trabaja DENTRO de la transacción de quien llama y NO confirma: así la
    ingesta puede guardar la lectura, llamar al motor de alertas (``evaluar_lectura``) y hacer un
    único ``commit``, de modo que la lectura y sus alertas se guardan juntas o no se guarda nada
    (contrato de alertas, sección 8, punto 9). Si algo falla, deshacer es cosa de quien llama.
    """
    # Integridad de los datos, no regla de negocio: SQLite convierte NaN en nulo (y la columna no
    # admite nulos) e ``inf`` se guardaría pero luego rompe el JSON y las gráficas. La API también
    # lo valida, pero el simulador y el histórico escriben aquí directamente, sin pasar por ella.
    if not math.isfinite(value):
        raise ValueError(f"Valor no válido para una lectura: {value!r}")
    when = _as_utc(timestamp)

    if session is not None:
        stored = _insert_reading(session, sensor_id, when, value)
    else:
        with conexion.open_session() as own:
            stored = _insert_reading(own, sensor_id, when, value)
            # Un único commit: la lectura y su ``last_seen_at`` se guardan juntas o nada.
            own.commit()

    return s.IngestResult(
        sensor_id=sensor_id, timestamp=when.astimezone(timezone.utc), stored=stored,
        duplicate=not stored
    )


def _insert_reading(session: Session, sensor_id: str, when: datetime, value: float) -> bool:
    """El trabajo de ``save_reading`` dentro de una sesión, sin confirmar. ``True`` si la guardó."""
    if session.get(Sensor, sensor_id) is None:
        raise NotFoundError(f"El sensor {sensor_id!r} no existe")

    # "Inserta, y si ya existe esa pareja (sensor, hora), no hagas nada". Es UNA sola
    # instrucción que decide la base de datos, así que no hay hueco entre "comprobar si
    # existe" y "insertar" por el que se cuele otra petición a la vez. El índice único
    # ``uq_sensor_data_sensor_recorded`` es lo que detecta la repetida. Además, como no lanza
    # error, no estropea la transacción de quien llama.
    inserted = session.exec(
        sqlite_insert(SensorData)
        .values(sensor_id=sensor_id, recorded_at=when, value=value)
        .on_conflict_do_nothing(index_elements=["sensor_id", "recorded_at"])
    ).rowcount  # 1 = se insertó, 0 = ya existía
    if inserted != 1:
        return False

    # "Pon last_seen_at = esta hora, pero solo si estaba vacío o era anterior". También lo decide
    # la base de datos en una instrucción. ``synchronize_session="fetch"`` actualiza además el
    # sensor si ya está cargado en esta sesión (p. ej. la API lo leyó para validarlo): sin ello,
    # el motor de alertas, que lo lee en la misma sesión, vería el ``last_seen_at`` viejo.
    session.exec(
        update(Sensor)
        .where(Sensor.id == sensor_id)
        .where(or_(Sensor.last_seen_at.is_(None), Sensor.last_seen_at < when))
        .values(last_seen_at=when)
        .execution_options(synchronize_session="fetch")
    )
    return True


def readings(
    sensor_id: str, since: datetime | None = None, limit: int = 100
) -> list[s.Reading]:
    """Las últimas ``limit`` lecturas de un sensor, de la más antigua a la más reciente.

    - ``since``: solo las POSTERIORES a esa fecha (exclusivo). Así quien pregunta cada pocos
      segundos pasa la fecha de la última que ya tiene y no recibe repetidas.
    - Se quedan las ``limit`` MÁS RECIENTES (no las más antiguas), pero se devuelven ordenadas
      de antigua a reciente, que es lo que necesita una gráfica.
    - Sensor inexistente, sin lecturas o ``limit <= 0``: lista vacía.
    """
    if limit <= 0:
        return []  # en SQLite un LIMIT negativo significa "sin límite": se evita
    with conexion.open_session() as session:
        sensor = session.get(Sensor, sensor_id)
        if sensor is None:
            return []
        query = select(SensorData).where(SensorData.sensor_id == sensor_id)
        if since is not None:
            query = query.where(SensorData.recorded_at > _as_utc(since))
        # Se piden de más reciente a más antigua para que LIMIT corte por el lado correcto...
        rows = session.exec(query.order_by(SensorData.recorded_at.desc()).limit(limit)).all()
        # ...y se dan la vuelta para devolverlas en orden cronológico.
        return [_reading(row, sensor) for row in reversed(rows)]


def last_reading(sensor_id: str) -> s.Reading | None:
    """La lectura más reciente de un sensor, o ``None`` si no existe o nunca ha enviado datos."""
    found = readings(sensor_id, limit=1)
    return found[0] if found else None


def last_readings(parcel_id: int) -> dict[str, s.Reading]:
    """La última lectura de cada sensor de la parcela, en UNA sola consulta (para el dashboard).

    Devuelve ``{código_del_sensor: lectura}``. Los sensores sin datos no aparecen en el
    diccionario, y una parcela inexistente da un diccionario vacío. Incluye los sensores
    desactivados que tengan lecturas.
    """
    with conexion.open_session() as session:
        # Paso 1: para cada sensor de la parcela, la fecha de su lectura más reciente.
        newest = (
            select(SensorData.sensor_id, func.max(SensorData.recorded_at).label("recorded_at"))
            .join(Sensor, Sensor.id == SensorData.sensor_id)
            .where(Sensor.parcel_id == parcel_id)
            .group_by(SensorData.sensor_id)
            .subquery()
        )
        # Paso 2: la fila completa de esas lecturas. Como (sensor, fecha) es único, cada pareja
        # da exactamente una fila.
        rows = session.exec(
            select(SensorData, Sensor)
            .join(
                newest,
                and_(
                    SensorData.sensor_id == newest.c.sensor_id,
                    SensorData.recorded_at == newest.c.recorded_at,
                ),
            )
            .join(Sensor, Sensor.id == SensorData.sensor_id)
        ).all()
        return {data.sensor_id: _reading(data, sensor) for data, sensor in rows}


# ---------------------------------------------------------------------------------------
# Parcelas: escrituras
# ---------------------------------------------------------------------------------------


def set_boundary(parcel_id: int, boundary: s.Polygon, area_m2: float) -> s.ParcelDetail | None:
    """Guarda el contorno dibujado de la parcela y su superficie.

    La superficie la calcula la API (``geo.polygon_area_m2``): el repositorio no la calcula ni la
    comprueba, solo la guarda junto al contorno. Sustituye el contorno anterior, si lo había.
    Devuelve la parcela ya actualizada, o ``None`` si no existe.
    """
    with conexion.open_session() as session:
        row = session.get(Parcel, parcel_id)
        if row is None:
            return None
        # SQLite no tiene tipo JSON: el contorno se guarda como texto GeoJSON y ``_parcel_detail``
        # lo convierte de nuevo en ``Polygon`` al leerlo.
        row.boundary = boundary.model_dump_json()
        row.area_m2 = area_m2
        session.commit()
        # Tras el commit la fila se vuelve a leer sola; la conversión se hace con la sesión abierta.
        return _parcel_detail(row)


def set_parcel_active(parcel_id: int, active: bool) -> s.Parcel | None:
    """Da de baja (``False``) o reactiva (``True``) una parcela Y TODOS sus sensores.

    Es una sola transacción: o cambia la parcela y todos sus sensores, o no cambia nada (si falla
    a mitad no puede quedar una parcela de baja con sensores activos que siguen generando alertas).
    Darla de baja no borra nada: las lecturas y alertas se conservan.

    Ojo: reactivar la parcela reactiva TODOS sus sensores, también los que alguien hubiera
    desactivado por separado antes de darla de baja. Así lo fija el contrato. Devuelve ``None``
    si la parcela no existe.
    """
    with conexion.open_session() as session:
        row = session.get(Parcel, parcel_id)
        if row is None:
            return None
        row.is_active = active
        # Un único UPDATE para todos los sensores de la parcela (no uno por sensor).
        session.exec(update(Sensor).where(Sensor.parcel_id == parcel_id).values(is_active=active))
        session.commit()  # parcela y sensores se confirman juntos, o ninguno
        return _parcel(row)


# ---------------------------------------------------------------------------------------
# Alertas (entrega 2)
#
# Abrir, cerrar y buscar la alerta activa NO está aquí: lo hace el motor de alertas de Mario L.
# (``demeter/services/alerts.py``) dentro de la transacción de la ingesta. Aquí está lo que
# necesitan la pantalla de alertas y el estado de conexión de los sensores.
# ---------------------------------------------------------------------------------------


def list_alerts(
    parcel_id: int | None = None,
    unread_only: bool = False,
    alert_type: str | None = None,
    sensor_id: str | None = None,
    active: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[s.Alert], int]:
    """Alertas, las más recientes primero, por páginas. Devuelve ``(página, total)``.

    Filtros (todos opcionales y combinables):
    - ``parcel_id``: solo las de los sensores de esa parcela.
    - ``unread_only``: solo las no leídas (``acknowledged=False``).
    - ``alert_type``: ``"LOW"``, ``"HIGH"`` u ``"OFFLINE"``.
    - ``sensor_id``: solo las de ese sensor.
    - ``active``: ``True`` solo activas (sin ``resolved_at``), ``False`` solo resueltas,
      ``None`` todas.

    ``total`` es cuántas cumplen los filtros SIN contar la paginación: es lo que la API manda en
    la cabecera ``X-Total-Count`` para que la interfaz sepa cuántas páginas hay.
    Con ``limit <= 0`` la página va vacía, pero ``total`` sigue siendo el real. Un ``offset``
    negativo lanza ``ValueError``.
    """
    if offset < 0:
        raise ValueError("offset no puede ser negativo")

    # Los filtros se escriben UNA vez y sirven para las dos consultas (página y total), así no
    # pueden quedar distintos.
    conditions = []
    if parcel_id is not None:
        conditions.append(
            Alert.sensor_id.in_(select(Sensor.id).where(Sensor.parcel_id == parcel_id))
        )
    if unread_only:
        conditions.append(Alert.acknowledged.is_(False))
    if alert_type is not None:
        conditions.append(Alert.type == alert_type)
    if sensor_id is not None:
        conditions.append(Alert.sensor_id == sensor_id)
    if active is True:
        conditions.append(Alert.resolved_at.is_(None))
    elif active is False:
        conditions.append(Alert.resolved_at.is_not(None))

    with conexion.open_session() as session:
        total = session.exec(select(func.count()).select_from(Alert).where(*conditions)).one()
        if limit <= 0:
            return [], total  # en SQLite un LIMIT negativo significa "sin límite": se evita
        rows = session.exec(
            select(Alert)
            .where(*conditions)
            # A igual hora de apertura, el id desempata: así el orden es siempre el mismo y la
            # paginación no repite ni salta alertas.
            .order_by(Alert.opened_at.desc(), Alert.id.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return [_alert(row) for row in rows], total


def set_acknowledged(alert_id: int, acknowledged: bool) -> s.Alert | None:
    """Marca una alerta como leída (``True``) o no leída (``False``). ``None`` si no existe.

    Solo cambia ``acknowledged``: leerla no la resuelve. Resolver lo decide el motor.
    """
    with conexion.open_session() as session:
        row = session.get(Alert, alert_id)
        if row is None:
            return None
        row.acknowledged = acknowledged
        session.commit()
        return _alert(row)


def acknowledge_all(parcel_id: int) -> int:
    """Marca como leídas todas las alertas sin leer de la parcela. Devuelve cuántas ha marcado.

    Es lo que usa ``POST /api/alerts/ack-all?parcel_id=``. Las que ya estaban leídas no cuentan,
    así que repetir la llamada devuelve 0. Una parcela inexistente o sin alertas también da 0.
    """
    with conexion.open_session() as session:
        changed = session.exec(
            update(Alert)
            .where(Alert.acknowledged.is_(False))
            .where(Alert.sensor_id.in_(select(Sensor.id).where(Sensor.parcel_id == parcel_id)))
            .values(acknowledged=True)
        ).rowcount
        session.commit()
        return changed


def sensors_last_seen() -> list[tuple[str, datetime | None]]:
    """``(código, last_seen_at)`` de los sensores ACTIVOS de parcelas ACTIVAS, por código.

    Solo lectura. Sirve para mostrar el estado de conexión (conectado / esperando datos / sin
    señal). ``None`` significa que el sensor nunca ha enviado datos: está "esperando", no caído.
    Las fechas van en UTC con zona.
    """
    with conexion.open_session() as session:
        rows = session.exec(
            select(Sensor.id, Sensor.last_seen_at)
            .join(Parcel, Parcel.id == Sensor.parcel_id)
            .where(Sensor.is_active, Parcel.is_active)
            .order_by(Sensor.id)
        ).all()
        return [(code, seen) for code, seen in rows]


# ---------------------------------------------------------------------------------------
# Usuarios (entrega 3)
#
# Las funciones de BÚSQUEDA devuelven el modelo ``User`` de la base de datos, no el esquema
# ``s.User``: el login necesita ``password_hash`` y el esquema no lo lleva (contrato, regla 2).
# Se devuelven ya desligados de la sesión, con todos sus campos cargados, así que se pueden leer
# sin problema; pero modificarlos NO cambia la base de datos: para eso está ``update_user``.
#
# El repositorio comprueba la integridad de los datos (correo en minúsculas, sin duplicados,
# alguna forma de entrar). Quién puede crear o cambiar usuarios lo decide la API.
# ---------------------------------------------------------------------------------------

_ROLES = {"admin", "tecnico", "lector"}
_USER_EDITABLE = {"role", "is_active", "email_verified", "password_hash", "google_sub"}
_USER_NOT_NULL = {"role", "is_active", "email_verified"}  # no admiten ``None``


def _user(row: User) -> s.User:
    # ``email`` y ``email_verified`` se pasan aunque ``s.User`` aún no los tenga: Pydantic ignora
    # los campos que el esquema no declara, y en cuanto Alex los añada saldrán sin tocar nada aquí.
    return s.User(
        id=row.id,
        username=row.username,
        role=row.role,
        is_active=row.is_active,
        email=row.email,
        email_verified=row.email_verified,
    )


def _normalize_email(email: str) -> str:
    # "Ana@Correo.ES " y "ana@correo.es" son el mismo buzón: se guarda y se busca siempre igual.
    return email.strip().lower()


def _find_user(**where) -> User | None:
    """Busca un usuario por un campo y lo devuelve desligado de la sesión (ver arriba).

    Al cerrarse la sesión sin ``commit``, la fila queda desligada pero con todos sus campos ya
    leídos, así que se puede usar fuera. (Un ``commit`` sí los caducaría y fallaría al leerlos.)
    """
    with conexion.open_session() as session:
        query = select(User)
        for field, value in where.items():
            query = query.where(getattr(User, field) == value)
        return session.exec(query).first()


def get_user(user_id: int) -> User | None:
    """Un usuario por su id (la API lo usa en cada petición para leer el rol y si está activo)."""
    return _find_user(id=user_id)


def get_user_by_username(username: str) -> User | None:
    """Para el login con contraseña. Un usuario que solo entra con Google trae
    ``password_hash=None``: la API debe tratarlo como contraseña incorrecta."""
    return _find_user(username=username)


def get_user_by_email(email: str) -> User | None:
    """Para el registro y la recuperación de contraseña. Busca el correo en minúsculas."""
    return _find_user(email=_normalize_email(email))


def get_user_by_google_sub(google_sub: str) -> User | None:
    """Para el login con Google. Es la ÚNICA forma de enlazar una cuenta de Google: nunca por
    correo, porque quien controle un correo igual en Google podría entrar en otra cuenta."""
    return _find_user(google_sub=google_sub)


def list_users() -> list[s.User]:
    """Todos los usuarios por orden de id, también los desactivados. Sin contraseña."""
    with conexion.open_session() as session:
        return [_user(row) for row in session.exec(select(User).order_by(User.id)).all()]


def _check_unique(session: Session, user_id: int | None, **values) -> None:
    """Lanza ``AlreadyExistsError`` si otro usuario ya tiene alguno de esos valores.

    Se comprueba antes de guardar para poder decir QUÉ campo está repetido (la base de datos solo
    diría "UNIQUE constraint failed"). ``user_id`` excluye al propio usuario al editarlo.
    """
    for field, value in values.items():
        if value is None:
            continue  # varios usuarios pueden no tener google_sub
        query = select(User.id).where(getattr(User, field) == value)
        if user_id is not None:
            query = query.where(User.id != user_id)
        if session.exec(query).first() is not None:
            raise AlreadyExistsError(f"Ya existe un usuario con ese {field}")


def create_user(
    username: str,
    email: str,
    role: str,
    password_hash: str | None = None,
    google_sub: str | None = None,
    email_verified: bool = False,
) -> s.User:
    """Crea un usuario y lo devuelve sin contraseña.

    - Necesita ``password_hash`` o ``google_sub`` (o los dos): si no, nadie podría entrar con él
      (``ValueError``; la base de datos también lo impide).
    - El ``username`` no puede llevar ``@``: así un texto con ``@`` en el login es siempre un
      correo y nunca se confunde con un nombre de usuario (``ValueError``).
    - ``role`` debe ser ``admin``, ``tecnico`` o ``lector`` (``ValueError``).
    - El correo se guarda en minúsculas.
    - ``username``, ``email`` o ``google_sub`` repetidos: ``AlreadyExistsError``.
    - ``password_hash`` llega ya calculado: cifrar la contraseña es cosa de la API
      (``security.hash_password``), el repositorio nunca ve la contraseña en claro.
    """
    username = username.strip()
    email = _normalize_email(email)
    if not username or "@" in username:
        raise ValueError("El nombre de usuario no puede estar vacío ni llevar @")
    if not email:
        raise ValueError("El correo no puede estar vacío")
    if role not in _ROLES:
        raise ValueError(f"Rol no válido: {role!r}")
    if password_hash is None and google_sub is None:
        raise ValueError("Hace falta password_hash o google_sub para poder entrar")

    with conexion.open_session() as session:
        _check_unique(session, None, username=username, email=email, google_sub=google_sub)
        row = User(
            username=username, email=email, role=role, password_hash=password_hash,
            google_sub=google_sub, email_verified=email_verified,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError as error:
            # Dos registros simultáneos con el mismo dato: los dos pasan la comprobación de arriba
            # y el índice único de la base de datos frena al segundo. Se traduce al error propio.
            raise AlreadyExistsError("Ya existe un usuario con esos datos") from error
        return _user(row)


def update_user(user_id: int, changes: dict) -> s.User | None:
    """Cambia SOLO los campos que vienen en ``changes``, como ``update_sensor``.

    Editables: ``role``, ``is_active`` (cuenta habilitada), ``email_verified`` (correo
    confirmado), ``password_hash`` y ``google_sub``. ``is_active`` y ``email_verified`` son cosas
    distintas: una cuenta puede estar confirmada y deshabilitada.

    - Otra clave: ``ValueError``, sin cambiar nada. ``username`` y ``email`` no se editan aquí.
    - ``None`` en ``role``, ``is_active`` o ``email_verified``: ``ValueError``.
    - ``None`` en ``password_hash`` o ``google_sub`` lo deja vacío (p. ej. desenlazar Google),
      pero no se pueden quedar los DOS vacíos: ``ValueError``.
    - ``google_sub`` de otro usuario: ``AlreadyExistsError``. Usuario inexistente: ``None``.
    """
    unknown = set(changes) - _USER_EDITABLE
    if unknown:
        raise ValueError(f"Campos no editables en un usuario: {sorted(unknown)}")
    for field in _USER_NOT_NULL & set(changes):
        if changes[field] is None:
            raise ValueError(f"{field} no puede ser None")
    if "role" in changes and changes["role"] not in _ROLES:
        raise ValueError(f"Rol no válido: {changes['role']!r}")

    with conexion.open_session() as session:
        row = session.get(User, user_id)
        if row is None:
            return None
        # Cómo quedarían las credenciales tras el cambio, antes de tocar nada.
        password_hash = changes.get("password_hash", row.password_hash)
        google_sub = changes.get("google_sub", row.google_sub)
        if password_hash is None and google_sub is None:
            raise ValueError("El usuario se quedaría sin forma de entrar")
        if "google_sub" in changes:
            _check_unique(session, user_id, google_sub=google_sub)
        for field, value in changes.items():
            setattr(row, field, value)
        try:
            session.commit()
        except IntegrityError as error:
            raise AlreadyExistsError("Ya existe un usuario con ese google_sub") from error
        return _user(row)
