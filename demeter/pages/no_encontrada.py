"""Página 404 con Demetreo (C2, issue #29): la que ve cualquier ruta que no exista."""

import reflex as rx

from demeter.components import prototipo
from demeter.components.layout import layout


@rx.page(route="404", title="Página no encontrada · Demeter")
def no_encontrada() -> rx.Component:
    return layout(
        prototipo.contenido("no_encontrada", "app p-404", scripts=("mascota.js",)),
        barra="acceso",
    )
