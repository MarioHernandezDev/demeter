"""``/ajustes``: umbrales de los sensores (solo admin), exportación y cuenta."""

import reflex as rx

from demeter.components.layout import cabecera, hueco, layout
from demeter.state.auth import AuthState


@rx.page(route="/ajustes", title="Ajustes · Demeter", on_load=AuthState.require_login)
def ajustes() -> rx.Component:
    return layout(
        cabecera("Ajustes", "Umbrales, exportación de datos y tu cuenta."),
        rx.el.div(
            rx.cond(
                AuthState.is_admin,
                hueco("Umbrales por sensor", "feature/ui-umbrales"),
                hueco("Umbrales por sensor", "feature/ui-umbrales", "Solo el administrador puede editarlos."),
            ),
            hueco("Exportar datos", "feature/exportacion", "CSV del histórico."),
            class_name="dm-rejilla",
        ),
        activa="/ajustes",
    )
