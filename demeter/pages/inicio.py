"""``/``: portada pública (C2, issue #29).

Es la portada del prototipo «Demeter web completa con Demetreo griego»: la Costa
Tropical con el nombre detrás de Sierra Nevada y, al bajar, la niebla y el bancal
que se dibuja en líneas (``assets/proto/intro.js``, con Three.js), seguida de la
cabina con los cuatro «mundos» (medir, avisar, regar, explorar).

Decisión del equipo: ``/`` no redirige; es la portada que ve el jurado. «Ver el
panel en vivo» lleva a ``/dashboard`` con sesión y al login sin ella.
"""

import reflex as rx

from demeter.components import prototipo
from demeter.components.layout import layout


@rx.page(route="/", title="Demeter · sensores de parcela en tiempo real")
def inicio() -> rx.Component:
    return layout(
        prototipo.contenido("inicio", "", niebla=False, scripts=("intro.js", "mascota.js"), app=False),
        barra="portada",
    )
