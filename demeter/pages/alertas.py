"""``/alertas``: maqueta del prototipo dentro de ``layout()`` (C2, issue #29).

Requiere sesión. El contenido es la plantilla ``plantillas/alertas.html`` con datos de
ejemplo; la rama de esta pantalla la sustituye por componentes con datos de la API
(ver ``demeter/components/prototipo.py``).
"""

import reflex as rx

from demeter.components import prototipo
from demeter.components.layout import layout
from demeter.state.auth import AuthState


@rx.page(route="/alertas", title="Alertas · Demeter", on_load=AuthState.require_login)
def alertas() -> rx.Component:
    return layout(
        prototipo.contenido("alertas", "app has-tabs p-alertas", scripts=("app.js", "mascota.js")),
        activa="/alertas",
    )
