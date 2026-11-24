"""Repositorio de datos (B6, issue #13): las consultas a la base de datos que usan la API, el
motor de alertas, el simulador y la interfaz.

El contrato (qué funciones hay, qué reciben y qué devuelven) está en
``docs/repositorio-contrato.md``. Reglas que se cumplen en TODAS las funciones:

- Cada función abre su propia sesión y la cierra al terminar: quien la llama no gestiona nada.
- Devuelven los esquemas de la API (``demeter.api.schemas``), nunca las filas de la base de
  datos, así que lo devuelto sigue siendo válido cuando la sesión ya está cerrada.
- Una consulta de algo que no existe devuelve ``None`` (o una lista vacía), no un error.
"""

from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlmodel import select

from demeter.api import schemas as s
from demeter.db import conexion
from demeter.models import Parcel, Sensor, SensorData

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


def _parcel(row: Parcel) -> s.Parcel:
    return s.Parcel(
        id=row.id,
        name=row.name,
        location=row.location,
        crop=row.crop,
        latitude=row.latitude,
        longitude=row.longitude,
        area_m2=row.area_m2,
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


def save_reading(sensor_id: str, timestamp: datetime, value: float) -> s.IngestResult:
    """Guarda una lectura. Una repetida (mismo sensor y misma hora) NO es un error.

    - Sensor inexistente: ``NotFoundError``.
    - Lectura repetida: no se guarda otra y devuelve ``stored=False, duplicate=True``. Los
      sensores reintentan cuando no reciben respuesta, así que repetir es normal.
    - ``sensors.last_seen_at`` solo AVANZA: una lectura atrasada se guarda, pero no lo mueve
      hacia atrás (si no, un reenvío de datos viejos haría parecer caído un sensor que funciona).
    """
    when = _as_utc(timestamp)
    with conexion.open_session() as session:
        if session.get(Sensor, sensor_id) is None:
            raise NotFoundError(f"El sensor {sensor_id!r} no existe")

        # "Inserta, y si ya existe esa pareja (sensor, hora), no hagas nada". Es UNA sola
        # instrucción que decide la base de datos, así que no hay hueco entre "comprobar si
        # existe" y "insertar" por el que se cuele otra petición a la vez. El índice único
        # ``uq_sensor_data_sensor_recorded`` es lo que detecta la repetida.
        inserted = session.exec(
            sqlite_insert(SensorData)
            .values(sensor_id=sensor_id, recorded_at=when, value=value)
            .on_conflict_do_nothing(index_elements=["sensor_id", "recorded_at"])
        ).rowcount  # 1 = se insertó, 0 = ya existía
        stored = inserted == 1

        if stored:
            # "Pon last_seen_at = esta hora, pero solo si estaba vacío o era anterior".
            # Igual que antes, lo decide la base de datos en una sola instrucción.
            session.exec(
                update(Sensor)
                .where(Sensor.id == sensor_id)
                .where(or_(Sensor.last_seen_at.is_(None), Sensor.last_seen_at < when))
                .values(last_seen_at=when)
            )
        # Un único commit: la lectura y su ``last_seen_at`` se guardan juntas o no se guarda nada.
        session.commit()

    return s.IngestResult(
        sensor_id=sensor_id, timestamp=when.astimezone(timezone.utc), stored=stored,
        duplicate=not stored
    )


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
