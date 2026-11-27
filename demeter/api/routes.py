"""Endpoints de la API (contrato A1/A2, issue #20).

Todo lee y escribe en la base de datos a través del repositorio (``demeter.db.repositorio``) y
los servicios; ``sample_data`` ya no se usa aquí (solo lo usan los usuarios de ejemplo de las
pruebas y los tests de predicción y riego para generar series).

Permisos (login real con bcrypt y JWT, ver ``auth.py``; usuarios en la BD):
- lector: solo lectura.
- tecnico: lectura + editar terreno, costes y colocar sensores.
- admin: todo, incluidos usuarios y umbrales de sensores.
La ingesta (``POST /api/sensors/{id}/data``) no usa usuario sino la cabecera ``X-API-Key``.
"""

import asyncio
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, WebSocket, WebSocketDisconnect, WebSocketException

from demeter.api import schemas as s
from demeter.api.auth import ADMIN, ANY, EDITOR, UserStore, authenticate, get_user_store
from demeter.api.geo import polygon_area_m2
from demeter.api.security import create_access_token, decode_access_token, hash_password
from demeter.db import conexion
from demeter.db import repositorio as repo
from demeter.services.alert_rules import card_status
from demeter.services import history as history_service
from demeter.services import weather as weather_service
from demeter.services.forecast import predict_sensor
from demeter.services.irrigation import recommend
from demeter.services.alerts import evaluar_lectura

VERSION = "0.1.0-contrato"
INGEST_KEY = os.environ.get("DEMETER_INGEST_KEY", "demo-ingest-key")

RECENT_POINTS = 20  # valores del mini histórico de cada tarjeta
DASHBOARD_ALERTS = 5  # alertas que enseña el dashboard
WS_POLL_SECONDS = 2.0  # cada cuánto mira la BD el WebSocket del dashboard

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- dependencias
# (quién es el usuario y qué rol exige cada endpoint: ver demeter/api/auth.py)


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
    """Todos los usuarios, también los dados de baja (solo admin)."""
    return repo.list_users()


@router.post("/users", response_model=s.User, status_code=201, tags=["usuarios"])
def create_user(body: s.UserCreate, _: s.User = ADMIN):
    """Crea un usuario con contraseña. La contraseña se guarda cifrada (bcrypt) y nunca se devuelve.

    Nombre de usuario o correo ya usados: 409. El correo se guarda en minúsculas.
    """
    try:
        return repo.create_user(
            username=body.username, email=body.email, role=body.role,
            password_hash=hash_password(body.password),
        )
    except repo.AlreadyExistsError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.patch("/users/{user_id}", response_model=s.User, tags=["usuarios"])
def update_user(user_id: int, body: s.UserUpdate, admin: s.User = ADMIN):
    """Cambia el rol o da de baja o reactiva a un usuario (no se borra). Solo lo enviado.

    Para no quedarse sin acceso, un admin no puede quitarse a sí mismo el rol ni darse de baja,
    y siempre debe quedar al menos un admin activo (409).
    """
    changes = body.model_dump(exclude_unset=True)
    if any(changes.get(k) is None for k in changes):
        raise HTTPException(422, "role e is_active no pueden ser null")
    target = next((u for u in repo.list_users() if u.id == user_id), None)
    if target is None:
        raise HTTPException(404, "Usuario no encontrado")
    quita_admin = target.role == "admin" and target.is_active and (
        changes.get("role", "admin") != "admin" or changes.get("is_active", True) is False
    )
    if quita_admin:
        if target.id == admin.id:
            raise HTTPException(409, "No puedes quitarte a ti mismo el rol de admin ni darte de baja")
        if sum(u.role == "admin" and u.is_active for u in repo.list_users()) <= 1:
            raise HTTPException(409, "Debe quedar al menos un admin activo")
    updated = repo.update_user(user_id, changes) if changes else target
    return updated


# ---------------------------------------------------------------- parcelas y sensores
# Leen y escriben en la base de datos (repositorio de David, #13).


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
    """Da de baja o reactiva una parcela y, con ella, todos sus sensores.

    Reactivarla da 409 si otra parcela activa del mismo propietario ya usa su nombre (una dada de
    baja libera el nombre, y al volver tiene que seguir siendo único)."""
    try:
        parcel = repo.set_parcel_active(parcel_id, body.is_active)
    except repo.AlreadyExistsError as e:
        raise HTTPException(409, str(e))
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
    try:
        updated = repo.set_boundary(parcel_id, body.boundary, area)
    except ValueError as e:  # el repositorio también valida (contorno y superficie van juntos, rangos)
        raise HTTPException(422, str(e))
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


@router.get("/sensors/{sensor_id}/history", response_model=s.SensorHistory, tags=["sensores"])
def sensor_history(
    sensor_id: str,
    range: s.HistoryRange = Query(default="24h", description="24h (tramos de 10 min), 7d (1 h) o 30d (6 h)"),
    user: s.User = ANY,
):
    """Histórico agregado para las gráficas (mín., media y máx. por tramo) y el resumen del rango,
    que Ajustes usa para enseñar «cómo fue la semana» de un sensor junto a sus límites."""
    sensor = _readable_sensor(sensor_id, user)
    since, until, step, buckets = history_service.aggregate(sensor_id, range)
    summary = history_service.summarize(buckets)
    return s.SensorHistory(
        sensor_id=sensor_id, type=sensor.type, unit=sensor.unit, range=range, since=since,
        until=until, bucket_minutes=int(step.total_seconds() // 60),
        threshold_low=sensor.threshold_low, threshold_high=sensor.threshold_high,
        points=[s.HistoryPoint(time=b.start, min=b.minimum, avg=b.average, max=b.maximum, count=b.count)
                for b in buckets],
        summary=None if summary is None else s.HistorySummary(
            min=summary.minimum, avg=summary.average, max=summary.maximum, count=summary.count),
    )


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


def _weather_or_none(parcel: s.Parcel) -> Optional[s.Weather]:
    if parcel.latitude is None or parcel.longitude is None:
        return None  # sin coordenadas no se puede pedir el clima
    return weather_service.get_weather(parcel.id, parcel.latitude, parcel.longitude)


def build_dashboard(parcel_id: int, user: s.User) -> s.DashboardSummary:
    """El resumen del dashboard de una parcela, tal y como lo ve ``user`` (lo usan GET y WebSocket)."""
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
        updated_at=now, weather=_weather_or_none(parcel), water=_water_summary(parcel_id),
    )


@router.get("/dashboard", response_model=s.DashboardSummary, tags=["dashboard"])
def dashboard(parcel_id: int = Query(default=1), user: s.User = ANY):
    """Último valor de cada sensor, alertas recientes, clima y agua de la parcela.

    Sensores y alertas salen de la base de datos. ``water`` sigue siendo de ejemplo hasta que
    exista el endpoint de agua; ``weather`` es el clima real (o ``null`` si no se pudo obtener).
    Para recibirlo sin preguntar cada pocos segundos, ver el WebSocket ``/api/ws/dashboard``.
    """
    return build_dashboard(parcel_id, user)


@router.websocket("/ws/dashboard")
async def dashboard_ws(
    websocket: WebSocket,
    parcel_id: int = Query(default=1),
    token: str = Query(default=""),
    store: UserStore = Depends(get_user_store),
):
    """El dashboard en vivo: se envía al conectar y de nuevo cada vez que algo cambia.

    - Un navegador no puede poner cabeceras en un WebSocket, así que el token JWT del login va
      en la URL: ``/api/ws/dashboard?parcel_id=1&token=...``.
    - Cada mensaje es ``{"type": "dashboard", "data": <lo mismo que GET /api/dashboard>}``.
    - El servidor mira la BD cada ``WS_POLL_SECONDS`` y solo envía si cambió algo (no cuenta
      ``updated_at``). Si el cliente manda ``ping`` responde ``{"type": "pong"}``.
    - Se cierra con el código 1008 si el token falta o no vale, si la parcela no existe o no se
      puede ver, o si más tarde el token caduca o el usuario es dado de baja.
    """
    def current():
        user_id = decode_access_token(token)
        stored = store.get_by_id(user_id) if user_id is not None else None
        return stored.user if stored and stored.user.is_active else None

    user = current()
    if user is None:
        raise WebSocketException(code=1008, reason="Token no válido")
    try:
        await asyncio.to_thread(build_dashboard, parcel_id, user)
    except HTTPException:
        raise WebSocketException(code=1008, reason="Parcela no encontrada")

    await websocket.accept()
    sent = None
    try:
        while True:
            user = current()
            if user is None:
                await websocket.close(code=1008, reason="Token caducado o usuario de baja")
                return
            try:
                summary = await asyncio.to_thread(build_dashboard, parcel_id, user)
            except HTTPException:  # la dieron de baja mientras tanto
                await websocket.close(code=1008, reason="Parcela no disponible")
                return
            snapshot = summary.model_dump_json(exclude={"updated_at"})
            if snapshot != sent:
                sent = snapshot
                await websocket.send_json(
                    {"type": "dashboard", "data": json.loads(summary.model_dump_json())}
                )
            try:
                # Esperar un mensaje del cliente hace de temporizador y a la vez avisa si se va.
                message = await asyncio.wait_for(websocket.receive_text(), WS_POLL_SECONDS)
                if message.strip() == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        return


@router.get("/alerts", response_model=list[s.Alert], tags=["alertas"])
def list_alerts(
    response: Response,
    parcel_id: Optional[int] = None,
    unread_only: bool = False,
    type: Optional[s.AlertType] = None,
    sensor_id: Optional[str] = None,
    active: Optional[bool] = Query(default=None, description="true: activas; false: resueltas"),
    since: Optional[datetime] = Query(default=None, description="Solo las abiertas desde esta fecha (ISO 8601), p. ej. los últimos 7 días"),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: s.User = ANY,
):
    """Alertas, las más recientes primero. La cabecera ``X-Total-Count`` dice cuántas hay en total."""
    if parcel_id is not None:
        _visible_parcel(parcel_id, user)
    page, total = repo.list_alerts(
        parcel_id=parcel_id, unread_only=unread_only, alert_type=type, sensor_id=sensor_id,
        active=active, limit=limit, offset=offset, opened_since=since,
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
def get_weather(parcel_id: int, user: s.User = ANY):
    """Clima real (Open-Meteo): tiempo actual y previsión de las próximas 24 h.

    Se guarda 10 min en memoria. Si no hay internet se devuelven los últimos datos conocidos con
    ``stale=true`` (hasta 6 h); si no hay ninguno, 503. Nunca se inventa un clima.
    """
    parcel, _ = _visible_parcel(parcel_id, user)
    weather = _weather_or_none(parcel)
    if weather is None:
        raise HTTPException(503, "No se pudo obtener el clima ahora mismo. Inténtalo en un minuto.")
    return weather


def _water_summary(parcel_id: int) -> s.WaterSummary:
    """Agua disponible de la parcela: depósitos con su nivel (último valor de su sensor) y una
    propuesta de reparto proporcional a la superficie de cultivo. El reparto de verdad, con el
    clima y la humedad del suelo, es el consejo de riego (``/irrigation``)."""
    tanks = repo.tanks(parcel_id)
    capacity = sum(x.capacity_l for x in tanks)
    available = round(sum(x.available_l or 0 for x in tanks), 1)
    terrain = repo.get_terrain(parcel_id)
    crop_zones = [z for z in (terrain.zones if terrain else []) if z.type == "crop"]
    crop_area = sum(z.area_m2 or 0 for z in crop_zones)
    shares = [
        s.WaterShare(
            zone_id=z.id, zone_name=z.name, liters=round(available * (z.area_m2 or 0) / crop_area, 1),
            share_pct=round(100 * (z.area_m2 or 0) / crop_area, 1),
            reason="Proporcional a la superficie de cultivo (m²)",
        )
        for z in crop_zones
    ] if crop_area else []
    return s.WaterSummary(
        parcel_id=parcel_id, total_capacity_l=capacity, available_l=available,
        level_pct=round(100 * available / capacity, 1) if capacity else 0.0,
        tanks=tanks, distribution=shares,
    )


@router.get("/parcels/{parcel_id}/water", response_model=s.WaterSummary, tags=["agua"])
def get_water(parcel_id: int, user: s.User = ANY):
    """Depósitos y agua disponible. El nivel sale de la última lectura del sensor de cada depósito
    (``null`` si aún no hay lecturas: no se sabe, que no es lo mismo que vacío)."""
    _visible_parcel(parcel_id, user)
    return _water_summary(parcel_id)


# ---------------------------------------------------------------- insights (predicción y riego)

PREDICTION_HISTORY = timedelta(hours=72)  # cuánto histórico se le da al motor de predicción


@router.get("/sensors/{sensor_id}/prediction", response_model=s.SensorPrediction, tags=["insights"])
def sensor_prediction(sensor_id: str, user: s.User = ANY):
    """Predicción a 24 h con las lecturas guardadas. Sin datos suficientes, 404."""
    sensor = _readable_sensor(sensor_id, user)
    now = datetime.now(timezone.utc)
    history = repo.readings(sensor_id, since=now - PREDICTION_HISTORY, limit=5000)
    pred = predict_sensor(sensor, ((r.timestamp, r.value) for r in history), now)
    if pred is None:
        raise HTTPException(404, "No hay datos suficientes para predecir")
    return pred


@router.get("/parcels/{parcel_id}/irrigation", response_model=s.IrrigationAdvice, tags=["insights"])
def irrigation_advice(parcel_id: int, user: s.User = ANY):
    """Consejo de riego con zonas, humedad del suelo, depósitos y clima reales. Sin previsión del
    tiempo (sin internet y sin nada guardado) el consejo es esperar: no se riega a ciegas."""
    parcel, _ = _visible_parcel(parcel_id, user)
    terrain = repo.get_terrain(parcel_id)
    last = repo.last_readings(parcel_id)
    soil = [
        (x, last[x.id].value if x.id in last else None)
        for x in (terrain.sensors if terrain else [])
        if x.type == "humedad_suelo" and x.is_active
    ]
    weather = _weather_or_none(parcel)
    return recommend(
        parcel_id, terrain.zones if terrain else [], soil, weather.forecast if weather else [],
        repo.tanks(parcel_id), datetime.now(timezone.utc), latitude=parcel.latitude,
    )


# ---------------------------------------------------------------- terreno 3D


def _editable_parcel(parcel_id: int, user: s.User) -> s.ParcelDetail:
    """La parcela, solo si se puede editar: existe, la ve el usuario y no está dada de baja."""
    parcel, active = _visible_parcel(parcel_id, user)
    if not active:
        raise HTTPException(409, "La parcela está dada de baja: reactívala antes de editarla")
    return parcel


@router.get("/parcels/{parcel_id}/terrain", response_model=s.Terrain, tags=["terreno"])
def terrain(parcel_id: int, user: s.User = ANY):
    """Todo lo del editor 3D en una llamada. Un lector no ve los sensores dados de baja."""
    parcel, _ = _visible_parcel(parcel_id, user)
    found = repo.get_terrain(parcel_id)
    sensors = found.sensors if user.role != "lector" else [x for x in found.sensors if x.is_active]
    return found.model_copy(update={"parcel": parcel, "sensors": sensors})


@router.post("/parcels/{parcel_id}/zones", response_model=s.Zone, status_code=201, tags=["terreno"])
def create_zone(parcel_id: int, body: s.ZoneCreate, user: s.User = EDITOR):
    _editable_parcel(parcel_id, user)
    try:
        area = polygon_area_m2(body.boundary)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return repo.create_zone(parcel_id, body, area)


@router.post("/parcels/{parcel_id}/elements", response_model=s.TerrainElement, status_code=201, tags=["terreno"])
def create_element(parcel_id: int, body: s.ElementCreate, user: s.User = EDITOR):
    _editable_parcel(parcel_id, user)
    return repo.create_element(parcel_id, body)


@router.delete("/elements/{element_id}", status_code=204, tags=["terreno"])
def delete_element(element_id: int, _: s.User = EDITOR):
    """Borra un elemento del terreno (lo único que se borra de verdad: un árbol mal colocado no
    tiene historial que conservar)."""
    if not repo.delete_element(element_id):
        raise HTTPException(404, "Elemento no encontrado")


# ---------------------------------------------------------------- costes e ingresos


@router.get("/parcels/{parcel_id}/transactions", response_model=list[s.Transaction], tags=["costes"])
def list_transactions(parcel_id: int, user: s.User = ANY):
    _visible_parcel(parcel_id, user)
    return repo.transactions(parcel_id)


@router.post("/parcels/{parcel_id}/transactions", response_model=s.Transaction, status_code=201, tags=["costes"])
def create_transaction(parcel_id: int, body: s.TransactionCreate, user: s.User = EDITOR):
    _editable_parcel(parcel_id, user)
    return repo.create_transaction(parcel_id, body)


@router.get("/parcels/{parcel_id}/balance", response_model=s.Balance, tags=["costes"])
def get_balance(parcel_id: int, user: s.User = ANY):
    _visible_parcel(parcel_id, user)
    return repo.balance(parcel_id)
