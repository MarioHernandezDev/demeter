"""``/parcelas``: maqueta del prototipo dentro de ``layout()`` (C2, issue #29).

Requiere sesión. El contenido es la plantilla ``plantillas/parcelas.html`` con datos de
ejemplo; la rama de esta pantalla la sustituye por componentes con datos de la API
(ver ``demeter/components/prototipo.py``).
"""

import reflex as rx

from demeter.components import prototipo
from demeter.components.layout import layout
from demeter.state.auth import AuthState


@rx.page(route="/parcelas", title="Parcelas · Demeter", on_load=AuthState.require_login)
def parcelas() -> rx.Component:
    return layout(
        prototipo.contenido("parcelas", "app has-tabs p-parcelas", scripts=("app.js", "mascota.js")),
        activa="/parcelas",
    )
