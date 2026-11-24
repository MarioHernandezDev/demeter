"""Endpoints de la API con respuestas de ejemplo (A1/A2, issue #20).

Todo devuelve datos inventados de ``sample_data``; las escrituras (POST/PUT/PATCH) validan la
entrada y devuelven lo que se «habría guardado», pero no persisten nada. Cuando exista la BD
(B1/B6) se sustituye cada llamada a ``sample_data`` por su consulta.

Permisos (login real con bcrypt y JWT, ver ``auth.py``; usuarios de ejemplo hasta que haya BD):
- lector: solo lectura.
- tecnico: lectura + editar terreno, costes y colocar sensores.
- admin: todo, incluidos usuarios y umbrales de sensores.
La ingesta (``POST /api/sensors/{id}/data``) no usa usuario sino la cabecera ``X-API-Key``.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from demeter.api import sample_data as d
from demeter.api import schemas as s
from demeter.api.auth import ADMIN, ANY, EDITOR, UserStore, authenticate, get_user_store
from demeter.api.geo import polygon_area_m2
from demeter.api.security import create_access_token
from demeter.db import conexion
from demeter.db import repositorio as repo
from demeter.services.alert_rules import card_status
from demeter.services.alerts import evaluar_lectura

VERSION = "0.1.0-contrato"
INGEST_KEY = os.environ.get("DEMETER_INGEST_KEY", "demo-ingest-key")

RECENT_POINTS = 20  # valores del mini histórico de cada tarjeta
DASHBOARD_ALERTS = 5  # alertas que enseña el dashboard

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- dependencias
# (quién es el usuario y qué rol exige cada endpoint: ver demeter/api/auth.py)


def _parcel(parcel_id: int) -> s.ParcelDetail:
    p = d.PARCELS.get(parcel_id)
    if p is None:
        raise HTTPException(404, "Parcela no encontrada")
    return p


def _sensor(sensor_id: str) -> s.Sensor:
    x = d.sensor_by_id(sensor_id)
    if x is None:
        raise HTTPException(404, "Sensor no encontrado")
    return x


# ---------------------------------------------------------------- salud y auth


@router.get("/health", response_model=s.Health, tags=["sistema"])
def health():
    return s.Health(version=VERSION)


@router.post("/auth/login", response_model=s.LoginResponse, tags=["auth"])
def login(body: s.LoginRequest, store: UserStore = Depends(get_user_store)):
    """Devuelve un token JWT (caduca en 60 min). Ejemplo: ``admin`` / ``demo1234``."""
    user = authenticate(store, body.username, body.password)
    if user is None:
        raise HTTPException(401, "Usuario o contraseña incorrectos")
    return s.LoginResponse(access_token=create_access_token(user.id), user=user)


@router.get("/auth/me", response_model=s.User, tags=["auth"])
def me(user: s.User = ANY):
    return user


@router.get("/users", response_model=list[s.User], tags=["usuarios"])
def list_users(_: s.User = ADMIN):
    return list(d.USERS.values())


@router.post("/users", response_model=s.User, status_code=201, tags=["usuarios"])
def create_user(body: s.UserCreate, _: s.User = ADMIN):
    if body.username in d.USERS:
        raise HTTPException(409, "Ese nombre de usuario ya existe")
    return s.User(id=d.new_id(), username=body.username, role=body.role)


@router.patch("/users/{user_id}", response_model=s.User, tags=["usuarios"])
def update_user(user_id: int, body: s.UserUpdate, _: s.User = ADMIN):
    user = next((u for u in d.USERS.values() if u.id == user_id), None)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    return user.model_copy(update=body.model_dump(exclude_none=True))


# ---------------------------------------------------------------- parcelas y sensores
# Estas rutas ya leen y escriben en la base de datos (repositorio de David, #13). El resto de
# rutas sigue con ``sample_data`` hasta que le toque a su tarea.


def _active_parcel_ids() -> set[int]:
    # Hasta que el repositorio rellene ``is_active`` en las parcelas, se deduce de aquí:
    # las que salen en la lista normal están activas y el resto está de baja.
    return {p.id for p in repo.list_parcels()}


def _visible_parcel(parcel_id: int, user: s.User) -> tuple[s.ParcelDetail, bool]:
    """La parcela y si está activa. Una dada de baja solo existe para un admin (404 al resto)."""
    parcel = repo.get_parcel(parcel_id)
    active = parcel_id in _active_parcel_ids() if parcel else False
    if parcel is None or (not active and user.role != "admin"):
        raise HTTPException(404, "Parcela no encontrada")
    return parcel.model_copy(update={"is_active": active}), active


@router.get("/parcels", response_model=list[s.Parcel], tags=["parcelas"])
def list_parcels(include_inactive: bool = False, user: s.User = ANY):
    """Parcelas activas. Con ``include_inactive=true`` también las de baja (solo admin)."""
    if include_inactive and user.role != "admin":
        raise HTTPException(403, "Solo un admin puede ver las parcelas dadas de baja")
    active = _active_parcel_ids()
    return [
        p.model_copy(update={"is_active": p.id in active})
        for p in repo.list_parcels(include_inactive=include_inactive)
    ]


@router.get("/parcels/{parcel_id}", response_model=s.ParcelDetail, tags=["parcelas"])
def get_parcel(parcel_id: int, user: s.User = ANY):
    return _visible_parcel(parcel_id, user)[0]


@router.patch("/parcels/{parcel_id}", response_model=s.Parcel, tags=["parcelas"])
def update_parcel(parcel_id: int, body: s.ParcelUpdate, _: s.User = ADMIN):
    """Da de baja o reactiva una parcela y, con ella, todos sus sensores."""
    parcel = repo.set_parcel_active(parcel_id, body.is_active)
    if parcel is None:
        raise HTTPException(404, "Parcela no encontrada")
    return parcel.model_copy(update={"is_active": body.is_active})


@router.put("/parcels/{parcel_id}/boundary", response_model=s.ParcelDetail, tags=["parcelas"])
def set_boundary(parcel_id: int, body: s.BoundaryUpdate, user: s.User = EDITOR):
    _, active = _visible_parcel(parcel_id, user)
    if not active:
        raise HTTPException(409, "La parcela está dada de baja: reactívala antes de editarla")
    try:
        area = polygon_area_m2(body.boundary)
    except ValueError as e:
        raise HTTPException(422, str(e))
    updated = repo.set_boundary(parcel_id, body.boundary, area)
    if updated is None:
        raise HTTPException(404, "Parcela no encontrada")
    return updated.model_copy(update={"is_active": True})


@router.get("/parcels/{parcel_id}/sensors", response_model=list[s.Sensor], tags=["sensores"])
def list_sensors(parcel_id: int, user: s.User = ANY):
    """Sensores de la parcela. Los dados de baja solo los ven admin y técnico."""
    _visible_parcel(parcel_id, user)
    sensors = repo.parcel_sensors(parcel_id)
    return sensors if user.role != "lector" else [x for x in sensors if x.is_active]


@router.patch("/sensors/{sensor_id}", response_model=s.Sensor, tags=["sensores"])
def update_sensor(sensor_id: str, body: s.SensorUpdate, user: s.User = EDITOR):
    sensor = repo.get_sensor(sensor_id)
    if sensor is None:
        raise HTTPException(404, "Sensor no encontrado")
    _, parcel_active = _visible_parcel(sensor.parcel_id, user)

    # Solo lo enviado: un campo ausente no se toca y uno con null se deja vacío.
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return sensor
    if user.role != "admin" and ({"threshold_low", "threshold_high"} & changes.keys()):
        raise HTTPException(403, "Solo un admin puede cambiar los umbrales")
    if "is_active" in changes:
        if changes["is_active"] is None:
            raise HTTPException(422, "is_active no puede ser null")
        if changes["is_active"] and not parcel_active:
            raise HTTPException(409, "La parcela está dada de baja: reactívala primero")

    # El mínimo debe ser menor que el máximo, mirando también lo que ya estaba guardado.
    low = changes.get("threshold_low", sensor.threshold_low)
    high = changes.get("threshold_high", sensor.threshold_high)
    if low is not None and high is not None and low >= high:
        raise HTTPException(422, "El umbral mínimo debe ser menor que el máximo")

    updated = repo.update_sensor(sensor_id, changes)
    if updated is None:
        raise HTTPException(404, "Sensor no encontrado")
    return updated


def _readable_sensor(sensor_id: str, user: s.User) -> s.Sensor:
    """El sensor, si el usuario puede verlo (un lector no ve los dados de baja ni los de parcelas de baja)."""
    sensor = repo.get_sensor(sensor_id)
    if sensor is None or (user.role == "lector" and not sensor.is_active):
        raise HTTPException(404, "Sensor no encontrado")
    _visible_parcel(sensor.parcel_id, user)
    return sensor


@router.get("/sensors/{sensor_id}/data", response_model=list[s.Reading], tags=["sensores"])
def sensor_data(
    sensor_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    since: Optional[str] = Query(default=None, description="ISO 8601; solo lecturas posteriores"),
    user: s.User = ANY,
):
    """Las últimas ``limit`` lecturas, de la más antigua a la más reciente."""
    _readable_sensor(sensor_id, user)
    t0 = None
    if since:
        try:
            t0 = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "«since» debe ser una fecha ISO 8601")
    return repo.readings(sensor_id, since=t0, limit=limit)


# Lo que se admite como hora de una lectura en vivo: algo de margen hacia atrás (una placa
# puede reenviar lo que no pudo mandar) y casi nada hacia delante (un reloj mal puesto).
MAX_PAST = timedelta(hours=24)
MAX_FUTURE = timedelta(minutes=5)
# El histórico puede ser tan antiguo como se quiera, pero no de antes de que existiera el sistema:
# las placas sin reloj arrancan en 1970 y eso es un error, no un dato.
OLDEST_HISTORY = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _check_ingest_key(x_api_key: Optional[str]) -> None:
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), INGEST_KEY.encode()):
        raise HTTPException(401, "X-API-Key incorrecta")


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@router.post("/sensors/{sensor_id}/data", response_model=s.IngestResult, tags=["ingesta"])
def ingest(sensor_id: str, body: s.ReadingIn, x_api_key: Optional[str] = Header(default=None)):
    """Entrada de lecturas en vivo (cabecera ``X-API-Key``).

    - Sin ``timestamp`` se usa la hora de llegada. Con él, debe estar entre 24 h atrás y 5 min
      por delante de la hora del servidor (si no, 422).
    - Una lectura repetida (mismo sensor y hora) se ignora: ``stored=false, duplicate=true``.
    - La lectura y sus alertas se guardan en una sola transacción. Solo una lectura nueva y no
      atrasada puede abrir o cerrar alertas (lo decide el motor de alertas).
    """
    _check_ingest_key(x_api_key)
    now = datetime.now(timezone.utc)
    when = _utc(body.timestamp) if body.timestamp else now
    if when < now - MAX_PAST or when > now + MAX_FUTURE:
        raise HTTPException(
            422, "La hora de la lectura debe estar entre 24 h antes y 5 min después de la del servidor"
        )
    with conexion.open_session() as session:
        try:
            result = repo.save_reading(sensor_id, when, body.value, session=session)
        except repo.NotFoundError:
            raise HTTPException(404, "Sensor no encontrado")
        if result.stored:
            evaluar_lectura(session, sensor_id, when, body.value)
        session.commit()
    return result


@router.post("/sensors/{sensor_id}/data/batch", response_model=s.BatchResult, tags=["ingesta"])
def ingest_history(
    sensor_id: str, body: s.ReadingBatchIn, x_api_key: Optional[str] = Header(default=None)
):
    """Carga de histórico (hasta 1000 lecturas por llamada), con ``X-API-Key``.

    Guarda todo o nada. **No genera alertas**: es historia, no lo que pasa ahora. Las repetidas
    se cuentan en ``duplicates`` y no son un error. Las horas deben ser de 2000 en adelante y
    no pasarse de 5 min del futuro.
    """
    _check_ingest_key(x_api_key)
    limit = datetime.now(timezone.utc) + MAX_FUTURE
    points = [(_utc(p.timestamp), p.value) for p in body.readings]
    if any(t < OLDEST_HISTORY or t > limit for t, _ in points):
        raise HTTPException(422, "Hay lecturas con una hora anterior al año 2000 o en el futuro")
    stored = 0
    with conexion.open_session() as session:
        try:
            for when, value in points:
                stored += repo.save_reading(sensor_id, when, value, session=session).stored
        except repo.NotFoundError:
            raise HTTPException(404, "Sensor no encontrado")
        session.commit()
    return s.BatchResult(
        sensor_id=sensor_id, received=len(points), stored=stored, duplicates=len(points) - stored
    )


# ---------------------------------------------------------------- dashboard, alertas, clima, agua


@router.get("/dashboard", response_model=s.DashboardSummary, tags=["dashboard"])
def dashboard(parcel_id: int = Query(default=1), user: s.User = ANY):
    """Último valor de cada sensor, alertas recientes, clima y agua de la parcela.

    Sensores y alertas salen de la base de datos. ``weather`` y ``water`` siguen siendo de
    ejemplo hasta que existan los endpoints de clima y agua.
    """
    parcel, _ = _visible_parcel(parcel_id, user)
    now = datetime.now(timezone.utc)
    sensors = repo.parcel_sensors(parcel_id)
    if user.role == "lector":
        sensors = [x for x in sensors if x.is_active]
    last = repo.last_readings(parcel_id)
    snaps = []
    for sensor in sensors:
        reading = last.get(sensor.id)
        snaps.append(s.SensorSnapshot(
            sensor=sensor,
            last=reading,
            status=card_status(
                reading.value if reading else None, reading.timestamp if reading else None,
                now, sensor.threshold_low, sensor.threshold_high,
            ),
            recent=[r.value for r in repo.readings(sensor.id, limit=RECENT_POINTS)],
        ))
    # Las 5 más recientes, las activas primero y después las ya resueltas.
    alerts, _total = repo.list_alerts(parcel_id=parcel_id, active=True, limit=DASHBOARD_ALERTS)
    if len(alerts) < DASHBOARD_ALERTS:
        alerts += repo.list_alerts(
            parcel_id=parcel_id, active=False, limit=DASHBOARD_ALERTS - len(alerts)
        )[0]
    unread = repo.list_alerts(parcel_id=parcel_id, unread_only=True, limit=0)[1]
    return s.DashboardSummary(
        parcel=s.Parcel(**parcel.model_dump(exclude={"boundary"})),
        sensors=snaps, alerts=alerts, unread_alerts=unread,
        updated_at=now, weather=d.weather(parcel_id), water=d.water(parcel_id),
    )


@router.get("/alerts", response_model=list[s.Alert], tags=["alertas"])
def list_alerts(
    response: Response,
    parcel_id: Optional[int] = None,
    unread_only: bool = False,
    type: Optional[s.AlertType] = None,
    sensor_id: Optional[str] = None,
    active: Optional[bool] = Query(default=None, description="true: activas; false: resueltas"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: s.User = ANY,
):
    """Alertas, las más recientes primero. La cabecera ``X-Total-Count`` dice cuántas hay en total."""
    if parcel_id is not None:
        _visible_parcel(parcel_id, user)
    page, total = repo.list_alerts(
        parcel_id=parcel_id, unread_only=unread_only, alert_type=type, sensor_id=sensor_id,
        active=active, limit=limit, offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    return page


@router.post("/alerts/ack-all", response_model=s.AckAllResult, tags=["alertas"])
def acknowledge_all_alerts(parcel_id: int = Query(), user: s.User = EDITOR):
    """Marca como leídas todas las alertas sin leer de la parcela."""
    _visible_parcel(parcel_id, user)
    return s.AckAllResult(updated=repo.acknowledge_all(parcel_id))


@router.patch("/alerts/{alert_id}", response_model=s.Alert, tags=["alertas"])
def update_alert(alert_id: int, body: s.AlertUpdate, _: s.User = EDITOR):
    alert = repo.set_acknowledged(alert_id, body.acknowledged)
    if alert is None:
        raise HTTPException(404, "Alerta no encontrada")
    return alert


@router.get("/parcels/{parcel_id}/weather", response_model=s.Weather, tags=["clima"])
def get_weather(parcel_id: int, _: s.User = ANY):
    _parcel(parcel_id)
    return d.weather(parcel_id)


@router.get("/parcels/{parcel_id}/water", response_model=s.WaterSummary, tags=["agua"])
def get_water(parcel_id: int, _: s.User = ANY):
    _parcel(parcel_id)
    return d.water(parcel_id)


# ---------------------------------------------------------------- insights (predicción y riego)


@router.get("/sensors/{sensor_id}/prediction", response_model=s.SensorPrediction, tags=["insights"])
def sensor_prediction(sensor_id: str, _: s.User = ANY):
    pred = d.prediction(_sensor(sensor_id))
    if pred is None:
        raise HTTPException(404, "No hay datos suficientes para predecir")
    return pred


@router.get("/parcels/{parcel_id}/irrigation", response_model=s.IrrigationAdvice, tags=["insights"])
def irrigation_advice(parcel_id: int, _: s.User = ANY):
    _parcel(parcel_id)
    return d.irrigation(parcel_id)


# ---------------------------------------------------------------- terreno 3D


@router.get("/parcels/{parcel_id}/terrain", response_model=s.Terrain, tags=["terreno"])
def terrain(parcel_id: int, _: s.User = ANY):
    p = _parcel(parcel_id)
    return s.Terrain(
        parcel=p,
        zones=[z for z in d.ZONES if z.parcel_id == parcel_id],
        elements=[e for e in d.ELEMENTS if e.parcel_id == parcel_id],
        sensors=d.parcel_sensors(parcel_id),
        tanks=d.tanks(parcel_id),
    )


@router.post("/parcels/{parcel_id}/zones", response_model=s.Zone, status_code=201, tags=["terreno"])
def create_zone(parcel_id: int, body: s.ZoneCreate, _: s.User = EDITOR):
    _parcel(parcel_id)
    try:
        area = polygon_area_m2(body.boundary)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return s.Zone(id=d.new_id(), parcel_id=parcel_id, area_m2=area, **body.model_dump())


@router.post("/parcels/{parcel_id}/elements", response_model=s.TerrainElement, status_code=201, tags=["terreno"])
def create_element(parcel_id: int, body: s.ElementCreate, _: s.User = EDITOR):
    _parcel(parcel_id)
    return s.TerrainElement(id=d.new_id(), parcel_id=parcel_id, **body.model_dump())


@router.delete("/elements/{element_id}", status_code=204, tags=["terreno"])
def delete_element(element_id: int, _: s.User = EDITOR):
    if not any(e.id == element_id for e in d.ELEMENTS):
        raise HTTPException(404, "Elemento no encontrado")


# ---------------------------------------------------------------- costes e ingresos


@router.get("/parcels/{parcel_id}/transactions", response_model=list[s.Transaction], tags=["costes"])
def list_transactions(parcel_id: int, _: s.User = ANY):
    _parcel(parcel_id)
    return d.transactions(parcel_id)


@router.post("/parcels/{parcel_id}/transactions", response_model=s.Transaction, status_code=201, tags=["costes"])
def create_transaction(parcel_id: int, body: s.TransactionCreate, _: s.User = EDITOR):
    _parcel(parcel_id)
    return s.Transaction(id=d.new_id(), parcel_id=parcel_id, **body.model_dump())


@router.get("/parcels/{parcel_id}/balance", response_model=s.Balance, tags=["costes"])
def get_balance(parcel_id: int, _: s.User = ANY):
    _parcel(parcel_id)
    return d.balance(parcel_id)
