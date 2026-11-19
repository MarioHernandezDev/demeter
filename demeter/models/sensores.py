"""Modelo de la tabla ``sensors`` (docs/modelo-datos.md, sección 3.3)."""

from datetime import datetime

from sqlmodel import Field, SQLModel

# Tipo de sensor -> unidad de medida (sección 5 del documento).
# La unidad no la elige el usuario: la pone el código a partir del tipo.
# Así no puede haber un sensor de temperatura medido en "%".
UNIDAD_POR_TIPO: dict[str, str] = {
    "temperatura": "ºC",
    "humedad_suelo": "%",
    "luminosidad": "klx",
    "humedad_ambiente": "%",
    "nivel_deposito": "%",
}


class Sensor(SQLModel, table=True):
    """Aparato instalado en una parcela. Cada sensor mide una sola magnitud."""

    __tablename__ = "sensors"

    # Clave primaria de TEXTO: el código del sensor tal como lo manda el
    # simulador y el reto ("t001", "h001"...). Cerrado con Alex: usamos ese
    # código directamente como clave, sin columna ``code`` aparte ni número
    # autoincremental. Por eso no lleva ``default``: lo da quien crea el sensor.
    id: str = Field(primary_key=True)

    # Clave foránea a la parcela donde está instalado.
    parcel_id: int = Field(foreign_key="parcels.id", index=True)

    # Una de las claves de UNIDAD_POR_TIPO. Se valida en la aplicación.
    type: str

    # Se rellena desde UNIDAD_POR_TIPO al crear el sensor.
    unit: str

    # Texto corto para mostrar ("Estación norte"). Puede ir vacío, pero no
    # nulo: así el código nunca tiene que comprobar si es ``None``.
    description: str = Field(default="")

    # Umbrales de alerta. Opcionales: un sensor sin umbrales no genera
    # alertas LOW/HIGH (solo OFFLINE, si deja de enviar datos).
    threshold_low: float | None = Field(default=None)
    threshold_high: float | None = Field(default=None)

    # Posición de instalación, introducida a mano. Opcional.
    latitude: float | None = Field(default=None)
    longitude: float | None = Field(default=None)

    is_active: bool = Field(default=True)

    # Última lectura recibida (UTC). Vacío = nunca ha enviado datos, y en ese
    # caso NO cuenta como caído (OFFLINE): un sensor recién dado de alta no
    # debe disparar una alerta por no haber hablado todavía.
    last_seen_at: datetime | None = Field(default=None)