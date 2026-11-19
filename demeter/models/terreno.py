"""Modelos del terreno 3D (docs/modelo-datos.md, secciones 4.1 a 4.3).

Las tres tablas guardan formas geográficas como texto GeoJSON, con el orden
[longitud, latitud]. El editor 3D las convierte a metros tomando como origen
el centro de la parcela (``parcels.latitude`` / ``parcels.longitude``).
"""

from sqlmodel import Field, SQLModel


class Zone(SQLModel, table=True):
    """Parte en que se divide una parcela (zona de cultivo o de no cultivo)."""

    __tablename__ = "zones"

    id: int | None = Field(default=None, primary_key=True)
    parcel_id: int = Field(foreign_key="parcels.id", index=True)
    name: str

    # ``crop`` (cultivo) | ``no_crop`` (no cultivo). Se valida en la aplicación.
    type: str

    # Qué se cultiva. Solo tiene sentido en zonas de cultivo, de ahí que sea opcional.
    crop: str | None = Field(default=None)

    # Polígono GeoJSON como texto. Obligatorio: una zona sin forma no se puede dibujar.
    boundary: str

    # Se guarda aunque se pueda calcular (decisión 20): la calcula el servidor
    # y hay que actualizarla cada vez que cambie el contorno.
    area_m2: float | None = Field(default=None)


class TerrainElement(SQLModel, table=True):
    """Objeto colocado en el editor 3D: árbol, bancal o camino.

    Los sensores NO van aquí (decisión 16): el editor los lee de ``sensors``
    para que no haya dos copias de lo mismo que se puedan desincronizar.
    """

    __tablename__ = "terrain_elements"

    id: int | None = Field(default=None, primary_key=True)
    parcel_id: int = Field(foreign_key="parcels.id", index=True)

    # ``tree`` | ``terrace`` | ``path``. Una sola tabla para los tres (decisión
    # 17) porque GeoJSON admite punto, línea y polígono en la misma columna.
    type: str

    # Detalle opcional: aguacate, mango, chirimoya...
    subtype: str | None = Field(default=None)

    # Punto (árbol), línea (camino) o polígono (bancal), en GeoJSON como texto.
    geometry: str

    # Altura en metros, solo para dibujar en 3D. Opcional (un camino no tiene).
    height_m: float | None = Field(default=None)


class Tank(SQLModel, table=True):
    """Depósito de agua. Puede haber varios por parcela."""

    __tablename__ = "tanks"

    id: int | None = Field(default=None, primary_key=True)
    parcel_id: int = Field(foreign_key="parcels.id", index=True)

    # El nivel NO es una columna (decisión 18): es la última lectura de este
    # sensor (tipo ``nivel_deposito``, en %). Así el depósito reutiliza el
    # histórico, las gráficas y las alertas sin construir nada aparte.
    # Opcional: un depósito puede existir sin sensor instalado. La clave
    # foránea es de TEXTO porque ``sensors.id`` es un código ("d001").
    level_sensor_id: str | None = Field(default=None, foreign_key="sensors.id")

    name: str

    # Los litros disponibles se calculan: capacity_l * nivel / 100.
    capacity_l: float

    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)