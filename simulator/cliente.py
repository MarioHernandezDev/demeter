"""Envío de una lectura a la API (B4, issue #15).

Usa ``urllib``, que viene con Python: el simulador no añade ninguna dependencia al proyecto.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Respuesta:
    """Qué pasó al mandar una lectura.

    ``estado`` es el código HTTP (200, 401, 404, 422...) o ``None`` si ni siquiera se pudo hablar
    con la API (está apagada, la dirección está mal...).
    """

    estado: int | None
    repetida: bool = False
    detalle: str = ""

    @property
    def ok(self) -> bool:
        return self.estado == 200


def enviar(
    api_url: str, api_key: str, sensor_id: str, instante: datetime, valor: float,
    timeout: float = 5.0,
) -> Respuesta:
    """Manda una lectura a ``POST {api_url}/api/sensors/{sensor_id}/data``. Nunca lanza
    excepciones: cualquier fallo vuelve como ``Respuesta``, y el bucle decide qué hacer."""
    url = f"{api_url.rstrip('/')}/api/sensors/{sensor_id}/data"
    # La hora va SIEMPRE con zona (``isoformat`` de una fecha UTC escribe "+00:00").
    cuerpo = json.dumps({"timestamp": instante.isoformat(), "value": valor}).encode()
    peticion = urllib.request.Request(
        url, data=cuerpo, method="POST",
        headers={"Content-Type": "application/json", "X-API-Key": api_key},
    )
    try:
        with urllib.request.urlopen(peticion, timeout=timeout) as respuesta:
            datos = json.loads(respuesta.read() or b"{}")
            return Respuesta(estado=respuesta.status, repetida=bool(datos.get("duplicate")))
    except urllib.error.HTTPError as error:
        # La API contestó, pero con un error (clave mala, sensor inexistente, hora fuera de rango).
        return Respuesta(estado=error.code, detalle=_detalle(error))
    except (urllib.error.URLError, OSError) as error:
        # No hubo respuesta: la API no está arrancada o no se llega a ella.
        return Respuesta(estado=None, detalle=str(getattr(error, "reason", error)))


def _detalle(error: urllib.error.HTTPError) -> str:
    try:
        return json.loads(error.read()).get("detail", "")
    except (ValueError, AttributeError):
        return ""
