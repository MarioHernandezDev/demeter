"""``layout()``: el marco común de todas las páginas (C2, issue #29).

- Escritorio: barra superior con la marca, la navegación, el contador de alertas y
  el usuario.
- Móvil (por debajo de ``theme.CORTE_MOVIL_PX``): la navegación pasa a cuatro
  pestañas fijas abajo, al alcance del pulgar. El cambio es solo CSS (``theme.py``),
  así que no hay parpadeo ni estado que sincronizar.

Uso::

    @rx.page(route="/parcelas", on_load=AuthState.require_login)
    def parcelas() -> rx.Component:
        return layout(contenido, activa="/parcelas")

Las páginas públicas (``/`` y ``/login``) pasan ``publica=True``: misma marca y
mismos estilos, sin la navegación de la app.
"""

from __future__ import annotations

from dataclasses import dataclass

import reflex as rx

from demeter.state.auth import AuthState
from demeter.state.ui import UIState


@dataclass(frozen=True)
class Seccion:
    """Una entrada de la navegación."""

    ruta: str
    texto: str
    icono: str  # nombre de icono de Lucide (rx.icon)


SECCIONES: tuple[Seccion, ...] = (
    Seccion("/dashboard", "Panel", "layout-dashboard"),
    Seccion("/parcelas", "Parcelas", "map"),
    Seccion("/alertas", "Alertas", "bell"),
    Seccion("/ajustes", "Ajustes", "settings"),
)


def _marca() -> rx.Component:
    return rx.el.a(
        rx.el.img(src="/logo.svg", alt=""),
        rx.el.span("DEMETER"),
        href="/",
        class_name="dm-marca",
        aria_label="Demeter, inicio",
    )


def _burbuja_alertas() -> rx.Component:
    """Contador de alertas sin leer; no se pinta si es 0."""
    return rx.cond(
        UIState.alertas_sin_leer > 0,
        rx.el.span(UIState.texto_alertas, class_name="dm-badge", aria_label="alertas sin leer"),
    )


def _enlace(s: Seccion, activa: str, movil: bool) -> rx.Component:
    hijos = [rx.icon(s.icono), rx.el.span(s.texto)] if movil else [s.texto]
    if s.ruta == "/alertas":
        hijos.append(_burbuja_alertas())
    return rx.el.a(
        *hijos,
        href=s.ruta,
        # aria-current marca la sección activa (también para lectores de pantalla).
        aria_current="page" if s.ruta == activa else None,
    )


def _usuario() -> rx.Component:
    return rx.cond(
        AuthState.is_authenticated,
        rx.el.div(
            rx.el.span(AuthState.username, class_name="dm-etiqueta dm-usuario"),
            rx.el.button("Salir", on_click=AuthState.logout, class_name="dm-boton dm-boton--sec"),
            class_name="dm-bar__fin",
        ),
        rx.el.div(
            rx.el.a("Entrar", href="/login", class_name="dm-boton"),
            class_name="dm-bar__fin",
        ),
    )


def layout(*contenido: rx.Component, activa: str = "", publica: bool = False) -> rx.Component:
    """Envuelve el contenido de una página con la barra (y las pestañas en móvil).

    Args:
        contenido: lo que va dentro de ``<main>``.
        activa: ruta de la sección actual, para resaltarla (``"/parcelas"``).
        publica: ``True`` en ``/`` y ``/login``: sin navegación de la app.
    """
    barra = [_marca()]
    if not publica:
        barra.append(rx.el.nav(*[_enlace(s, activa, movil=False) for s in SECCIONES], class_name="dm-nav"))
    barra.append(_usuario())

    partes = [
        rx.el.header(*barra, class_name="dm-bar"),
        rx.el.main(*contenido, class_name="dm-main"),
    ]
    if not publica:
        partes.append(
            rx.el.nav(
                *[_enlace(s, activa, movil=True) for s in SECCIONES],
                class_name="dm-pestanas",
                aria_label="Secciones",
            )
        )
    return rx.el.div(*partes, class_name="dm-shell" + (" dm-shell--publica" if publica else ""))


def hueco(titulo: str, rama: str, texto: str = "") -> rx.Component:
    """Tarjeta de sitio reservado: dice qué rama la rellena, para que nadie la pise."""
    return rx.el.div(
        rx.el.p(rama, class_name="dm-etiqueta"),
        rx.el.h3(titulo, style={"margin": "8px 0 6px"}),
        rx.el.p(texto, style={"margin": 0}) if texto else rx.fragment(),
        class_name="dm-tarjeta dm-hueco",
    )


def cabecera(titulo: str, sub: str = "") -> rx.Component:
    """Título y subtítulo de una página."""
    return rx.fragment(
        rx.el.h1(titulo, class_name="dm-titulo"),
        rx.el.p(sub, class_name="dm-sub") if sub else rx.fragment(),
    )
