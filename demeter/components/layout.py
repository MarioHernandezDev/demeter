"""``layout()``: el marco común de todas las páginas (C2, issue #29).

Reproduce la barra y las pestañas del prototipo «Demeter web completa con
Demetreo griego», pero en Reflex, para que la sesión, el contador de alertas y la
sección activa salgan del estado y no de HTML fijo:

- ``barra="app"`` (páginas con sesión): Panel · Parcelas · Alertas · Ajustes, el
  usuario y «Salir». En móvil (≤ 760 px, ``assets/proto/app.css``) la navegación
  pasa a una píldora de cuatro pestañas abajo, al alcance del pulgar.
- ``barra="portada"`` (``/``): los anclajes de la portada y «Ver el panel en vivo».
- ``barra="acceso"`` (``/login`` y la 404): solo la marca y «Volver al inicio».

Uso::

    @rx.page(route="/parcelas", on_load=AuthState.require_login)
    def parcelas() -> rx.Component:
        return layout(contenido, activa="/parcelas")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import reflex as rx

from demeter.state.auth import AuthState
from demeter.state.ui import UIState

Barra = Literal["app", "portada", "acceso"]


@dataclass(frozen=True)
class Seccion:
    """Una entrada de la navegación."""

    ruta: str
    texto: str


SECCIONES: tuple[Seccion, ...] = (
    Seccion("/dashboard", "Panel"),
    Seccion("/parcelas", "Parcelas"),
    Seccion("/alertas", "Alertas"),
    Seccion("/ajustes", "Ajustes"),
)

# Anclajes de la portada (secciones de demeter/pages/plantillas/inicio.html).
ANCLAS_PORTADA: tuple[tuple[str, str], ...] = (
    ("#panel", "Panel"),
    ("#cultivos", "Cultivos"),
    ("#gemelo", "Gemelo"),
    ("#api", "API"),
    ("#codigo", "Código"),
)


def _marca(href: str = "/") -> rx.Component:
    return rx.el.a(rx.el.span(class_name="ring", aria_hidden="true"), "Demeter", href=href, class_name="bar__logo")


def _enlace(s: Seccion, activa: str) -> rx.Component:
    hijos: list = [s.texto]
    if s.ruta == "/alertas":
        # Los scripts del prototipo leen y actualizan [data-unread]; por eso se pinta
        # siempre, vacío cuando no hay alertas.
        hijos.append(rx.el.b(UIState.texto_alertas, data_unread=""))
    return rx.el.a(*hijos, href=s.ruta, aria_current="page" if s.ruta == activa else None)


def _barra_app(activa: str) -> list[rx.Component]:
    return [
        _marca(),
        rx.el.nav(*[_enlace(s, activa) for s in SECCIONES], class_name="bar__nav", aria_label="Secciones"),
        rx.el.a(
            rx.el.span(AuthState.inicial),
            AuthState.username,
            href="/ajustes",
            class_name="bar__user",
            aria_label="Cuenta",
        ),
        rx.el.button("Salir", type="button", on_click=AuthState.logout, class_name="bar__cta bar__cta--ghost"),
    ]


def _barra_portada() -> list[rx.Component]:
    return [
        _marca("#top"),
        rx.el.nav(*[rx.el.a(t, href=h) for h, t in ANCLAS_PORTADA], class_name="bar__nav", aria_label="Principal"),
        rx.el.button("Ver el panel en vivo", type="button", on_click=AuthState.ir_al_panel, class_name="bar__cta"),
    ]


def _barra_acceso() -> list[rx.Component]:
    return [_marca(), rx.el.a("Volver al inicio", href="/", class_name="bar__cta bar__cta--ghost")]


def layout(*contenido: rx.Component, activa: str = "", barra: Barra = "app") -> rx.Component:
    """Barra superior + contenido (+ pestañas en móvil en las páginas con sesión).

    Args:
        contenido: el ``<main>`` de la página y lo que vaya detrás.
        activa: ruta de la sección actual (``"/parcelas"``), para ``aria-current``.
        barra: ``"app"``, ``"portada"`` o ``"acceso"`` (ver arriba).
    """
    piezas = {"app": lambda: _barra_app(activa), "portada": _barra_portada, "acceso": _barra_acceso}[barra]()
    partes = [rx.el.header(*piezas, class_name="bar"), *contenido]
    if barra == "app":
        partes.append(
            rx.el.nav(*[_enlace(s, activa) for s in SECCIONES], class_name="tabs", aria_label="Secciones")
        )
    return rx.el.div(*partes, class_name=f"dm-shell dm-shell--{barra}")
