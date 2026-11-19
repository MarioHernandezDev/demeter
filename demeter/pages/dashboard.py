"""``/dashboard``: panel con el último valor de cada sensor y las alertas activas.

C2 deja el marco; cada hueco dice qué rama lo rellena.
"""

import reflex as rx

from demeter.components.layout import cabecera, hueco, layout
from demeter.state.auth import AuthState


@rx.page(route="/dashboard", title="Panel · Demeter", on_load=AuthState.require_login)
def dashboard() -> rx.Component:
    return layout(
        cabecera("Panel", "Último valor de cada sensor y lo que necesita tu atención."),
        rx.el.div(
            hueco("Lecturas actuales", "feature/dashboard-tiempo-real", "Una tarjeta por sensor, en vivo."),
            hueco("Histórico", "feature/dashboard-graficas", "Gráficas con filtro desde / hasta."),
            hueco("Alertas activas", "feature/alertas-pagina"),
            hueco("Consejo de riego", "feature/insights", "Predicción a 24 h."),
            class_name="dm-rejilla",
        ),
        activa="/dashboard",
    )
