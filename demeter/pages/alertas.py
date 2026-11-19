"""``/alertas``: alertas abiertas y su historial."""

import reflex as rx

from demeter.components.layout import cabecera, hueco, layout
from demeter.state.auth import AuthState


@rx.page(route="/alertas", title="Alertas · Demeter", on_load=AuthState.require_login)
def alertas() -> rx.Component:
    return layout(
        cabecera("Alertas", "Valores fuera de umbral, de la más reciente a la más antigua."),
        rx.el.div(
            hueco("Alertas abiertas e historial", "feature/alertas-pagina"),
            hueco("Avisos fuera de la app", "feature/alertas-notificaciones"),
            class_name="dm-rejilla",
        ),
        activa="/alertas",
    )
