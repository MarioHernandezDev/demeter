"""Datos de ejemplo de la Costa Tropical (B3, issue #14).

Rellena la base de datos con lo mínimo para que la aplicación tenga algo que enseñar:
3 usuarios, 3 fincas, 14 sensores y un depósito de agua por finca. NO crea lecturas (de eso
se encarga el simulador, #15) ni el terreno 3D (zonas, elementos y movimientos).

Uso, con la base de datos ya migrada (``reflex db migrate``):

    python -m demeter.db.seed

Se puede ejecutar todas las veces que se quiera: solo crea lo que falta y nunca modifica ni
duplica lo que ya existe. Así ``reset_demo.py`` (#17) puede llamarlo sin miedo.
"""

import os

from sqlalchemy.exc import OperationalError
from sqlmodel import Session, select

from demeter.api.security import hash_password
from demeter.db.conexion import open_session
from demeter.models import Parcel, Sensor, Tank, User
from demeter.models.sensores import UNIDAD_POR_TIPO

# ---------------------------------------------------------------------------------------
# Los datos. Todo lo que se quiera cambiar de la demo está en esta sección.
# ---------------------------------------------------------------------------------------

# Contraseña de los tres usuarios de prueba. Es la misma que ya usa la API de ejemplo
# (``demo1234``) para que nada cambie al pasar a la base de datos. Es una contraseña de
# demostración: en un despliegue real se cambia con ``DEMETER_SEED_PASSWORD``.
DEMO_PASSWORD = os.environ.get("DEMETER_SEED_PASSWORD", "demo1234")

# (username, email, rol). El email va siempre en minúsculas (decisión 28 del modelo de datos)
# y el username no puede llevar «@» (decisión 27). Se marcan como verificados porque son
# cuentas de prueba: no hay correo al que mandar el enlace de verificación.
USERS = [
    ("admin", "admin@demeter.example", "admin"),
    ("tecnico", "tecnico@demeter.example", "tecnico"),
    ("lector", "lector@demeter.example", "lector"),
]

# (nombre, municipio, cultivo, latitud, longitud). Las coordenadas son el CENTRO de la finca.
# Todas pertenecen al usuario ``admin``.
PARCELS = [
    ("Finca La Costa", "Almuñécar", "aguacate", 36.7340, -3.6910),
    ("Huerta del Río", "Almuñécar", "mango", 36.7405, -3.6830),
    ("Vega de Motril", "Motril", "tomate", 36.7452, -3.5101),
]

# Umbrales de alerta por tipo de sensor: (mínimo, máximo). ``None`` = sin umbral por ese lado.
# Son los mismos que ya usan los datos de ejemplo de la API (``sample_data.py``).
THRESHOLDS = {
    "temperatura": (8, 35),
    "humedad_suelo": (25, 60),
    "luminosidad": (None, 100),
    "humedad_ambiente": (30, 85),
    "nivel_deposito": (20, None),
}

# (código, finca, tipo, descripción). El código es la clave del sensor: letra del tipo + número.
# Reparto 5 + 5 + 4 = 14. La finca de tomate no lleva luminosidad.
SENSORS = [
    ("t001", "Finca La Costa", "temperatura", "Estación norte"),
    ("h001", "Finca La Costa", "humedad_suelo", "Bancal 3"),
    ("l001", "Finca La Costa", "luminosidad", "Cubierta norte"),
    ("a001", "Finca La Costa", "humedad_ambiente", "Estación norte"),
    ("d001", "Finca La Costa", "nivel_deposito", "Balsa norte"),
    ("t002", "Huerta del Río", "temperatura", "Estación central"),
    ("h002", "Huerta del Río", "humedad_suelo", "Mangos"),
    ("l002", "Huerta del Río", "luminosidad", "Cubierta sur"),
    ("a002", "Huerta del Río", "humedad_ambiente", "Estación central"),
    ("d002", "Huerta del Río", "nivel_deposito", "Depósito de riego"),
    ("t003", "Vega de Motril", "temperatura", "Invernadero 1"),
    ("h003", "Vega de Motril", "humedad_suelo", "Tomates"),
    ("a003", "Vega de Motril", "humedad_ambiente", "Invernadero 1"),
    ("d003", "Vega de Motril", "nivel_deposito", "Balsa de riego"),
]

# (nombre, finca, capacidad en litros, sensor de nivel). Un depósito por finca, enlazado al
# sensor ``nivel_deposito`` de esa finca: el nivel del depósito es la última lectura de ese
# sensor (``repositorio.tanks``). Sin esta tabla, el agua disponible y el consejo de riego no
# tendrían de dónde sacar los litros. Se llaman igual que la descripción de su sensor.
TANKS = [
    ("Balsa norte", "Finca La Costa", 50_000, "d001"),
    ("Depósito de riego", "Huerta del Río", 20_000, "d002"),
    ("Balsa de riego", "Vega de Motril", 30_000, "d003"),
]


# ---------------------------------------------------------------------------------------
# La lógica: «crear si no existe».
# ---------------------------------------------------------------------------------------


def seed(session: Session) -> dict[str, int]:
    """Crea lo que falte y devuelve cuántas filas nuevas ha añadido de cada tabla.

    No hace ``commit``: quien la llama decide cuándo guardar. Si algo falla a medias, no
    queda nada guardado (todo o nada).
    """
    created = {"users": 0, "parcels": 0, "sensors": 0, "tanks": 0}

    # 1. Usuarios. Se buscan por username, que es único.
    # La huella bcrypt lleva sal propia, así que cada usuario tiene una distinta aunque
    # compartan contraseña. Solo se calcula si hay que crear el usuario: bcrypt es lento a
    # propósito y no tiene sentido gastarlo en usuarios que ya existen.
    users: dict[str, User] = {}
    for username, email, role in USERS:
        user = session.exec(select(User).where(User.username == username)).first()
        if user is None:
            user = User(
                username=username,
                email=email,
                email_verified=True,
                password_hash=hash_password(DEMO_PASSWORD),
                role=role,
            )
            session.add(user)
            created["users"] += 1
        users[username] = user

    # ``flush`` manda los usuarios a la base de datos SIN cerrar la transacción: así reciben
    # su ``id``, que las fincas necesitan como ``owner_id``.
    session.flush()

    # 2. Fincas. Se buscan por nombre; todas son del administrador.
    parcels: dict[str, Parcel] = {}
    for name, location, crop, lat, lon in PARCELS:
        parcel = session.exec(select(Parcel).where(Parcel.name == name)).first()
        if parcel is None:
            parcel = Parcel(
                owner_id=users["admin"].id,
                name=name,
                location=location,
                crop=crop,
                latitude=lat,
                longitude=lon,
            )
            session.add(parcel)
            created["parcels"] += 1
        parcels[name] = parcel
    session.flush()  # lo mismo: los sensores necesitan el ``id`` de su finca

    # 3. Sensores. La clave es el propio código ("t001"), así que ``get`` basta.
    for code, parcel_name, sensor_type, description in SENSORS:
        if session.get(Sensor, code) is None:
            low, high = THRESHOLDS[sensor_type]
            session.add(
                Sensor(
                    id=code,
                    parcel_id=parcels[parcel_name].id,
                    type=sensor_type,
                    # La unidad no se escribe a mano: sale del tipo, para que no pueda
                    # haber un sensor de temperatura medido en «%».
                    unit=UNIDAD_POR_TIPO[sensor_type],
                    description=description,
                    threshold_low=low,
                    threshold_high=high,
                )
            )
            created["sensors"] += 1
    session.flush()  # los depósitos apuntan a su sensor de nivel: tiene que existir antes

    # 4. Depósitos. No tienen nombre único en toda la base de datos (dos fincas podrían tener
    # una "Balsa"), así que se buscan por finca y nombre.
    for name, parcel_name, capacity_l, sensor_id in TANKS:
        parcel_id = parcels[parcel_name].id
        exists = session.exec(
            select(Tank).where(Tank.parcel_id == parcel_id, Tank.name == name)
        ).first()
        if exists is None:
            # Sin latitud ni longitud: la posición se coloca a mano en el editor 3D.
            session.add(
                Tank(
                    parcel_id=parcel_id,
                    name=name,
                    capacity_l=capacity_l,
                    level_sensor_id=sensor_id,
                )
            )
            created["tanks"] += 1

    return created


def main() -> int:
    try:
        with open_session() as session:
            created = seed(session)
            session.commit()
    except OperationalError as exc:
        # Lo más habitual: la base de datos existe pero sin tablas porque falta migrar.
        print(f"No se ha podido rellenar la base de datos: {exc.orig}")
        print("¿Has ejecutado antes `reflex db migrate`?")
        return 1

    print(
        f"Seed listo: {created['users']} usuarios, {created['parcels']} fincas, "
        f"{created['sensors']} sensores y {created['tanks']} depósitos nuevos."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
