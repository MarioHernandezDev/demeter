"""``Cabina3D``: la sección «mundos» de la portada como escena WebGL (three.js).

El componente React está en ``assets/cabina3d/cabina3d.jsx`` (librería local: Reflex lo copia a
``.web/public`` y lo importa en el build). ``three`` se instala como dependencia npm.

Los datos de los mundos viven en un solo sitio, ``assets/proto/cabina/mundos.json``: este módulo
los lee al compilar y se los pasa al componente; el fallback CSS (sin WebGL o con
``prefers-reduced-motion``) usa esos mismos datos.
"""

from __future__ import annotations

import json
from pathlib import Path

import reflex as rx
from reflex.vars import Var

MUNDOS_JSON = Path(__file__).resolve().parents[2] / "assets" / "proto" / "cabina" / "mundos.json"


def mundos() -> list[dict]:
    """Los mundos (proyectos) de la cabina, en el orden en que aparecen."""
    return json.loads(MUNDOS_JSON.read_text(encoding="utf-8"))


class Cabina3D(rx.Component):
    """Cabina de nave con ventanas: cilindro, mundos en capas, postprocesado y texto DOM."""

    library = rx.asset("cabina3d/cabina3d.jsx").importable_path
    tag = "Cabina3D"
    lib_dependencies: list[str] = ["three@0.160.0"]

    mundos: Var[list[dict]]


cabina3d = Cabina3D.create
