"""``/parcelas``: listado de parcelas y sus sensores."""

import reflex as rx

from demeter.components.layout import cabecera, hueco, layout
from demeter.state.auth import AuthState


@rx.page(route="/parcelas", title="Parcelas · Demeter", on_load=AuthState.require_login)
def parcelas() -> rx.Component:
    return layout(
        cabecera("Parcelas", "Tus fincas, sus sensores y dónde está cada uno."),
        rx.el.div(
            hueco("Listado de parcelas", "feature/ui-parcelas"),
            hueco("Mapa y gemelo 3D", "feature/ui-mapa"),
            class_name="dm-rejilla",
        ),
        activa="/parcelas",
    )
