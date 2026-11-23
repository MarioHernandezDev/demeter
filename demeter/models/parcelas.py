"""Modelo de la tabla ``parcels`` (docs/modelo-datos.md, sección 3.2)."""

from datetime import datetime

from sqlmodel import Field, SQLModel

from .base import ahora_utc


class Parcel(SQLModel, table=True):
    """Finca monitorizada. Cada parcela pertenece a un único usuario."""

    __tablename__ = "parcels"

    id: int | None = Field(default=None, primary_key=True)

    # Clave foránea: este número TIENE que ser el ``id`` de una fila de
    # ``users``. Así la base de datos puede impedir que exista una parcela
    # de un propietario que no existe (siempre que activemos las claves
    # foráneas en SQLite, algo que haremos en el repositorio, #13).
    # ``index=True`` acelera la consulta más frecuente: "las parcelas de
    # este usuario".
    owner_id: int = Field(foreign_key="users.id", index=True)

    name: str

    # Municipio o paraje, solo para mostrar en listas.
    location: str

    # Cultivo principal (aguacate, mango, tomate...).
    crop: str

    # Coordenadas del CENTRO de la parcela. Son obligatorias porque el
    # editor 3D las usa como origen (0, 0) para convertir los grados del
    # GeoJSON a metros. Sin centro no se puede dibujar el terreno.
    latitude: float
    longitude: float

    # Contorno en GeoJSON, guardado como texto (SQLite no tiene tipo
    # propio para JSON) con el orden [longitud, latitud]. Opcional: al
    # crear una parcela aún puede no estar dibujado.
    boundary: str | None = Field(default=None)

    # Superficie en m². La calcula el servidor a partir del contorno, así
    # que puede estar vacía hasta que haya contorno.
    area_m2: float | None = Field(default=None)

    # Dar de baja = desactivar, no borrar (decisión 24): se conserva el
    # historial de sensores y lecturas de esa parcela.
    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=ahora_utc)