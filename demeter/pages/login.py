"""``/login``: formulario de acceso (C2 lo maqueta; C3 #30 lo conecta a la API)."""

import reflex as rx

from demeter.components.layout import layout
from demeter.state.auth import AuthState


def _campo(nombre: str, etiqueta: str, tipo: str, autocompletar: str) -> rx.Component:
    return rx.el.label(
        rx.el.span(etiqueta, class_name="dm-etiqueta"),
        rx.el.input(
            name=nombre, type=tipo, auto_complete=autocompletar, required=True,
            style={"height": "44px", "padding": "0 14px", "border_radius": "12px", "font": "inherit",
                   "border": "1px solid var(--dm-linea)", "background": "var(--dm-papel)"},
        ),
        style={"display": "grid", "gap": "6px"},
    )


@rx.page(route="/login", title="Entrar · Demeter", on_load=AuthState.redirect_if_logged_in)
def login() -> rx.Component:
    return layout(
        rx.el.div(
            rx.el.h1("Entrar", class_name="dm-titulo"),
            rx.el.p("Accede al panel de tus parcelas.", class_name="dm-sub"),
            rx.el.form(
                _campo("username", "Usuario", "text", "username"),
                _campo("password", "Contraseña", "password", "current-password"),
                rx.cond(
                    AuthState.error != "",
                    rx.el.p(AuthState.error, role="alert", style={"margin": 0, "color": "var(--dm-acento)"}),
                ),
                rx.el.button(
                    rx.cond(AuthState.loading, "Entrando…", "Entrar"),
                    type="submit", disabled=AuthState.loading, class_name="dm-boton",
                ),
                on_submit=AuthState.login,
                style={"display": "grid", "gap": "16px"},
            ),
            class_name="dm-tarjeta",
            style={"max_width": "420px", "margin": "6vh auto 0", "padding": "32px"},
        ),
        publica=True,
    )
