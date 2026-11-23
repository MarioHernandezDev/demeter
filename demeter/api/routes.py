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

import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from demeter.api import sample_data as d
from demeter.api import schemas as s
from demeter.api.auth import ADMIN, ANY, EDITOR, UserStore, authenticate, get_user_store
from demeter.api.geo import polygon_area_m2
from demeter.api.security import create_access_token

VERSION = "0.1.0-contrato"
INGEST_KEY = os.environ.get("DEMETER_INGEST_KEY", "demo-ingest-key")

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


@router.get("/parcels", response_model=list[s.Parcel], tags=["parcelas"])
def list_parcels(_: s.User = ANY):
    return list(d.PARCELS.values())


@router.get("/parcels/{parcel_id}", response_model=s.ParcelDetail, tags=["parcelas"])
def get_parcel(parcel_id: int, _: s.User = ANY):
    return _parcel(parcel_id)


@router.put("/parcels/{parcel_id}/boundary", response_model=s.ParcelDetail, tags=["parcelas"])
def set_boundary(parcel_id: int, body: s.BoundaryUpdate, _: s.User = EDITOR):
    p = _parcel(parcel_id)
    try:
        area = polygon_area_m2(body.boundary)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return p.model_copy(update={"boundary": body.boundary, "area_m2": area})


@router.get("/parcels/{parcel_id}/sensors", response_model=list[s.Sensor], tags=["sensores"])
def list_sensors(parcel_id: int, _: s.User = ANY):
    _parcel(parcel_id)
    return d.parcel_sensors(parcel_id)


@router.patch("/sensors/{sensor_id}", response_model=s.Sensor, tags=["sensores"])
def update_sensor(sensor_id: str, body: s.SensorUpdate, user: s.User = EDITOR):
    sensor = _sensor(sensor_id)
    changes = body.model_dump(exclude_none=True)
    if user.role != "admin" and ({"threshold_low", "threshold_high"} & changes.keys()):
        raise HTTPException(403, "Solo un admin puede cambiar los umbrales")
    return sensor.model_copy(update=changes)


@router.get("/sensors/{sensor_id}/data", response_model=list[s.Reading], tags=["sensores"])
def sensor_data(
    sensor_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    since: Optional[str] = Query(default=None, description="ISO 8601; solo lecturas posteriores"),
    _: s.User = ANY,
):
    series = d.readings(_sensor(sensor_id))
    if since:
        from datetime import datetime

        try:
            t0 = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(422, "«since» debe ser una fecha ISO 8601")
        series = [r for r in series if r.timestamp > t0]
    return series[-limit:]


@router.post("/sensors/{sensor_id}/data", response_model=s.IngestResult, tags=["ingesta"])
def ingest(sensor_id: str, body: s.ReadingIn, x_api_key: Optional[str] = Header(default=None)):
    """Entrada de lecturas del simulador. Una lectura repetida (mismo sensor y hora) se ignora."""
    if x_api_key != INGEST_KEY:
        raise HTTPException(401, "X-API-Key incorrecta")
    _sensor(sensor_id)
    return s.IngestResult(sensor_id=sensor_id, timestamp=body.timestamp, stored=True)


# ---------------------------------------------------------------- dashboard, alertas, clima, agua


@router.get("/dashboard", response_model=s.DashboardSummary, tags=["dashboard"])
def dashboard(parcel_id: int = Query(default=1), _: s.User = ANY):
    parcel = _parcel(parcel_id)
    snaps = []
    for sensor in d.parcel_sensors(parcel_id):
        last = d.last_reading(sensor)
        status = d.compute_status(last.value if last else None, sensor.threshold_low, sensor.threshold_high)
        snaps.append(s.SensorSnapshot(sensor=sensor, last=last, status=status))
    alerts = d.alerts(parcel_id)
    return s.DashboardSummary(
        parcel=s.Parcel(**parcel.model_dump(exclude={"boundary"})),
        sensors=snaps, alerts=alerts, unread_alerts=sum(not a.acknowledged for a in alerts),
        updated_at=d.utc_now(), weather=d.weather(parcel_id), water=d.water(parcel_id),
    )


@router.get("/alerts", response_model=list[s.Alert], tags=["alertas"])
def list_alerts(parcel_id: Optional[int] = None, unread_only: bool = False, _: s.User = ANY):
    out = d.alerts(parcel_id)
    return [a for a in out if not a.acknowledged] if unread_only else out


@router.patch("/alerts/{alert_id}", response_model=s.Alert, tags=["alertas"])
def update_alert(alert_id: int, body: s.AlertUpdate, _: s.User = EDITOR):
    alert = next((a for a in d.alerts() if a.id == alert_id), None)
    if alert is None:
        raise HTTPException(404, "Alerta no encontrada")
    return alert.model_copy(update={"acknowledged": body.acknowledged})


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
