"""``/``: portada pública (C2, issue #29).

Es la portada del prototipo «Demeter web completa con Demetreo griego»: la Costa
Tropical con el nombre detrás de Sierra Nevada y, al bajar, la niebla y el bancal
que se dibuja en líneas (``assets/proto/intro.js``, con Three.js), seguida de la
cabina con los cuatro «mundos» (medir, avisar, regar, explorar): el componente
``Cabina3D`` (``demeter/components/cabina3d.py``), que va en el marcador ``@mundos`` de
la plantilla. Debajo, el gemelo 3D que se parte en tres al bajar
(``assets/proto/scroll-split.js``).

Decisión del equipo: ``/`` no redirige; es la portada que ve el jurado. «Ver el
panel en vivo» lleva a ``/dashboard`` con sesión y al login sin ella.
"""

import reflex as rx

from demeter.components import prototipo
from demeter.components.cabina3d import cabina3d, mundos
from demeter.components.layout import layout


# Sitio de la cabina en plantillas/inicio.html
MARCADOR_MUNDOS = "<!-- @mundos: aquí va el componente Cabina3D (demeter/components/cabina3d.jsx) -->"


@rx.page(route="/", title="Demeter · sensores de parcela en tiempo real")
def inicio() -> rx.Component:
    return layout(
        prototipo.contenido_con_centro(
            "inicio",
            MARCADOR_MUNDOS,
            cabina3d(mundos=mundos()),
            "",
            niebla=False,
            scripts=("intro.js", "scroll-split.js", "mascota.js"),
            app=False,
        ),
        barra="portada",
    )
