"""Rango físico posible de cada tipo de sensor.

Un valor fuera de este rango no es una medida rara: es un error (un cable suelto, una placa mal
calibrada, un reloj de otro sensor). Si entrara en la base de datos abriría alertas falsas, estropearía
las gráficas y las medias del histórico. Por eso la ingesta lo rechaza con un 422 en vez de guardarlo.

No son los umbrales de alerta (esos los elige el usuario y son más estrechos): son los límites de lo
que puede medir un sensor de este tipo, con margen. Un tipo que no esté aquí no se comprueba.
"""

from typing import Optional

PHYSICAL_RANGE: dict[str, tuple[float, float]] = {
    "temperatura": (-50.0, 100.0),  # ºC; los sensores baratos miden de -40 a 85 ºC
    "humedad_suelo": (0.0, 100.0),  # %
    "humedad_ambiente": (0.0, 100.0),  # %
    "nivel_deposito": (0.0, 100.0),  # % de llenado
    "luminosidad": (0.0, 200.0),  # klx; el sol directo ronda los 100
}


def out_of_range(sensor_type: str, value: float) -> Optional[str]:
    """Un texto que explica el problema si ``value`` es imposible para el tipo, o ``None`` si vale."""
    limits = PHYSICAL_RANGE.get(sensor_type)
    if limits is None:
        return None
    low, high = limits
    if low <= value <= high:
        return None
    return f"{value:g} está fuera del rango físico de un sensor de {sensor_type} ({low:g} a {high:g})"
