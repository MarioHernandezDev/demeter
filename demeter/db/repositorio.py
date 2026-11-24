"""Repositorio de datos (B6, issue #13): las consultas a la base de datos que usan la API, el
motor de alertas, el simulador y la interfaz.

El contrato (qué funciones hay, qué reciben y qué devuelven) está en
``docs/repositorio-contrato.md``. Reglas que se cumplen en TODAS las funciones:

- Cada función abre su propia sesión y la cierra al terminar: quien la llama no gestiona nada.
- Devuelven los esquemas de la API (``demeter.api.schemas``), nunca las filas de la base de
  datos, así que lo devuelto sigue siendo válido cuando la sesión ya está cerrada.
- Una consulta de algo que no existe devuelve ``None`` (o una lista vacía), no un error.
"""

from sqlmodel import select

from demeter.api import schemas as s
from demeter.db import conexion
from demeter.models import Parcel, Sensor

# ---------------------------------------------------------------------------------------
# Errores
# ---------------------------------------------------------------------------------------


class NotFoundError(Exception):
    """Una escritura apunta a algo que no existe (p. ej. una lectura de un sensor inexistente)."""


class AlreadyExistsError(Exception):
    """Se intenta crear algo único que ya existe (``username``, ``email`` o ``google_sub``)."""


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
