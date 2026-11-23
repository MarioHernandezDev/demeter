"""``/login``: acceso con fondo «Aurora» y Demetreo (C3 #30).

Diseño elegido en el prototipo «Login Demeter» (variante Aurora):

- Fondo WebGL con la paleta de Demeter y la palabra «Demeter» gigante detrás.
- Caja de cristal centrada con el formulario.
- Demetreo llega corriendo, se sienta sobre la caja, sigue con los ojos lo que escribes en
  «Usuario» y se tapa los ojos al escribir la contraseña (con «Mostrar» espía con uno).

El formulario es Reflex: envía a ``AuthState.login`` y pinta ``AuthState.error``. Demetreo y
el fondo son solo decoración (``aria-hidden``) y viven en ``assets/login/``; el estado real
del formulario lo anuncia el ``<p role="alert">`` del error.
"""

from functools import lru_cache
from pathlib import Path

import reflex as rx

from demeter.components import prototipo
from demeter.components.layout import layout
from demeter.state.auth import AuthState

SVG_DEMETREO = Path(__file__).resolve().parent.parent / "components" / "demetreo_login.svg"
FOTOGRAMAS = 6  # assets/login/img/demetreo-1..6.webp: la llegada corriendo


@lru_cache(maxsize=None)
def _svg_demetreo() -> str:
    """El Demetreo vivo del login (SVG). Sus ojos, manos y boca los mueve ``demetreo.js``."""
    return SVG_DEMETREO.read_text(encoding="utf-8")


def _demetreo() -> list[rx.Component]:
    """Bocadillo + Demetreo + los fotogramas de su llegada."""
    llegada = rx.el.div(
        rx.el.span(class_name="pl4__shade"),
        rx.el.div(
            *[
                rx.el.img(
                    src=f"/login/img/demetreo-{n}.webp",
                    alt="",
                    width="280",
                    height="330",
                    class_name=f"pl4__f pl4__f{n}",
                )
                for n in range(1, FOTOGRAMAS + 1)
            ],
            class_name="pl4__run",
        ),
        class_name="pl4__runway",
    )
    return [
        # Lo que dice Demetreo lo escribe el JS (decorativo).
        rx.el.div(
            rx.el.span("🥑", id="av-bubble-emoji"),
            rx.el.span("¡Hola! Listo para entrar", id="av-bubble-text"),
            id="av-bubble",
            class_name="pl4__bubble",
            aria_hidden="true",
        ),
        rx.el.div(rx.html(_svg_demetreo()), llegada, id="av-wrap", class_name="pl4__av", aria_hidden="true"),
    ]


def _campo(etiqueta: str, para: str, input_: rx.Component, *extra: rx.Component) -> rx.Component:
    return rx.el.div(
        rx.el.label(etiqueta, html_for=para, class_name="pl-label"),
        rx.el.div(input_, *extra, class_name="pl-control"),
        class_name="pl-field",
    )


def _formulario() -> rx.Component:
    # Con error, los dos campos se marcan como inválidos (borde y lectores de pantalla).
    invalido = rx.cond(AuthState.error != "", "true", "false")
    usuario = rx.el.input(
        id="pl4-username",
        name="username",
        auto_complete="username",
        default_value="tecnico",
        spell_check=False,
        auto_capitalize="none",
        aria_invalid=invalido,
        aria_describedby="pl4-err",
        class_name="pl-input",
    )
    contrasena = rx.el.input(
        id="pl4-password",
        name="password",
        type="password",
        auto_complete="current-password",
        aria_invalid=invalido,
        aria_describedby="pl4-err",
        class_name="pl-input",
    )
    # «Mostrar» lo gestiona demetreo.js: cambia el tipo del campo y la pose de Demetreo.
    mostrar = rx.el.button(
        "Mostrar",
        type="button",
        id="pl4-ojo",
        aria_pressed="false",
        aria_controls="pl4-password",
        class_name="pl4__ojo",
    )
    return rx.el.form(
        _campo("Usuario", "pl4-username", usuario),
        _campo("Contraseña", "pl4-password", contrasena, mostrar),
        rx.el.p(AuthState.error, id="pl4-err", class_name="pl-err", role="alert"),
        rx.el.button(
            rx.cond(AuthState.loading, "Entrando…", "Entrar"),
            type="submit",
            disabled=AuthState.loading,
            class_name="pl4__btn",
        ),
        on_submit=AuthState.login,
        class_name="pl4__form",
        no_validate=True,
    )


@rx.page(route="/login", title="Entrar · Demeter", on_load=AuthState.redirect_if_logged_in)
def login() -> rx.Component:
    return layout(
        rx.el.link(rel="stylesheet", href="/proto/proto.css"),
        rx.el.link(rel="stylesheet", href="/login/login.css"),
        rx.el.main(
            rx.el.section(
                rx.el.div(rx.el.span("Demeter", class_name="pl4__big"), class_name="pl4__deco", aria_hidden="true"),
                rx.el.canvas(class_name="pl4__fx", aria_hidden="true"),
                rx.el.div(
                    *_demetreo(),
                    rx.el.div(
                        rx.el.div(
                            rx.el.p("Acceso · técnicos y agricultores", class_name="pl-kick"),
                            rx.el.h1("Entra a ", rx.el.em("tu panel."), class_name="pl4__h"),
                            _formulario(),
                            class_name="pl4__body",
                        ),
                        rx.el.div(rx.el.span("Demo: tecnico / demo1234", class_name="pl4__demo"), class_name="pl4__dash"),
                        class_name="pl4__box",
                    ),
                    class_name="pl4__right",
                ),
                class_name="pl4",
            ),
            class_name="pl-login",
            id="top",
        ),
        prototipo.preparar("p-login", niebla=False, scripts=()),
        # Scripts de la decoración, como módulos (?v= para que se ejecuten de nuevo al volver).
        rx.el.div(
            hidden=True,
            on_mount=rx.call_script(
                "(() => { const v = Date.now();"
                " import('/login/fondo.js?v=' + v); import('/login/demetreo.js?v=' + v); })()"
            ),
        ),
        barra="acceso",
    )
