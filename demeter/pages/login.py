"""``/login``: acceso con el diseño del prototipo (C2 lo maqueta; C3 #30 lo conecta a la API).

A diferencia del resto de pantallas, el formulario ya es Reflex: envía a
``AuthState.login`` y pinta ``AuthState.error``, así C3 solo tiene que tocar el estado.
"""

import reflex as rx

from demeter.components import prototipo
from demeter.components.layout import layout
from demeter.state.auth import AuthState


def _campo(etiqueta: str, **attrs) -> rx.Component:
    return rx.el.label(etiqueta, rx.el.input(**attrs), class_name="field")


def _formulario() -> rx.Component:
    return rx.el.form(
        _campo("Usuario", name="username", auto_complete="username", placeholder="tecnico", default_value="tecnico"),
        _campo("Contraseña", name="password", type="password", auto_complete="current-password", placeholder="••••••••"),
        rx.el.p(AuthState.error, class_name="login__err", role="alert"),
        rx.el.div(
            rx.el.button(
                rx.cond(AuthState.loading, "Entrando…", "Entrar"),
                type="submit",
                disabled=AuthState.loading,
                class_name="login__btn",
            ),
            rx.el.span("Demo: tecnico / demo1234", class_name="login__hint"),
            class_name="login__row",
        ),
        on_submit=AuthState.login,
        class_name="login",
        no_validate=True,
    )


@rx.page(route="/login", title="Entrar · Demeter", on_load=AuthState.redirect_if_logged_in)
def login() -> rx.Component:
    return layout(
        *prototipo.hojas(),
        rx.el.main(
            rx.el.section(
                rx.el.div(
                    rx.el.p("Acceso · técnicos y agricultores", class_name="kick"),
                    rx.el.h1("Entra a", rx.el.br(), rx.el.em("tu panel."), class_name="h"),
                    rx.el.p("Tus parcelas, su histórico y los avisos, en tiempo real.", class_name="enter__txt"),
                    _formulario(),
                    class_name="enter__form",
                ),
                rx.el.figure(
                    rx.el.img(src="/proto/img/mundos/medir.webp", alt=""),
                    rx.el.figcaption(rx.el.i(), "Invernadero 2 · Carchuna · aire 27,4 ºC", class_name="mono", data_ticker=""),
                    class_name="enter__win",
                    aria_hidden="true",
                ),
                class_name="enter",
            ),
            id="top",
        ),
        rx.el.div(class_name="toast", role="status", hidden=True),
        prototipo.preparar("app is-login p-entrar", scripts=("app.js", "mascota.js")),
        barra="acceso",
    )
