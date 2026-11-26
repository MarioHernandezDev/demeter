"""Modo oscuro y pantalla de carga: el botón sol/luna de la barra y lo que va en el ``<head>``.

- El estado es el modo de color de Reflex (clase ``dark``/``light`` en ``<html>`` y
  ``localStorage.theme``); su script del ``<head>`` lo aplica antes de pintar.
- ``assets/proto/tema.js`` hace el cambio con una mancha de tinta que sale del botón y se
  extiende deshaciéndose en vetas y humo (campo en WebGL2 + View Transitions + filtro SVG);
  ``assets/proto/tema.css`` tiene el botón y la paleta oscura.
"""

from __future__ import annotations

import math

import reflex as rx

HOJA = "/proto/tema.css"
SCRIPT = "/proto/tema.js"
S = rx.el.svg  # elementos SVG (mask, circle, line…)


def cabeza() -> list[rx.Component]:
    """Para ``head_components`` de la app (en todas las páginas): tema y pantalla de carga.

    La pantalla de carga (el aguacate que gira, ``assets/proto/carga.css``) es CSS puro y se ve
    desde el primer pintado; ``carga.js`` la quita cuando la página está lista.
    """
    return [
        rx.el.link(rel="stylesheet", href=HOJA),
        rx.el.link(rel="stylesheet", href="/proto/carga.css"),
        rx.el.link(rel="preload", href="/proto/img/carga/aguacate-frente.svg", custom_attrs={"as": "image"}),
        rx.el.link(rel="preload", href="/proto/img/carga/aguacate-dorso.svg", custom_attrs={"as": "image"}),
        rx.el.script(src=SCRIPT, defer=True),
        rx.el.script(src="/proto/carga.js", defer=True),
    ]


def _rayo(k: int) -> rx.Component:
    a = k * math.pi / 4
    c, s = math.cos(a), math.sin(a)
    return S.line(x1=f"{12 + 8 * c:.2f}", y1=f"{12 + 8 * s:.2f}", x2=f"{12 + 10.5 * c:.2f}", y2=f"{12 + 10.5 * s:.2f}")


def _icono() -> rx.Component:
    """Sol que se vuelve luna: el «bocado» de la máscara entra en el disco y los rayos se recogen."""
    return S(
        S.mask(
            S.rect(x="0", y="0", width="24", height="24", fill="#fff"),
            S.circle(class_name="tema__bocado", cx="30", cy="-6", r="8", fill="#000"),
            id="dm-tema-mascara",
        ),
        S.circle(class_name="tema__astro", cx="12", cy="12", r="5", fill="currentColor", mask="url(#dm-tema-mascara)"),
        S.g(
            *[_rayo(k) for k in range(8)],
            class_name="tema__rayos",
            stroke="currentColor",
            stroke_width="2",
            stroke_linecap="round",
        ),
        view_box="0 0 24 24",
        class_name="tema__ico",
        aria_hidden="true",
    )


def boton_tema() -> rx.Component:
    """Botón de la barra que cambia entre claro y oscuro (lo maneja ``tema.js``)."""
    return rx.el.button(
        _icono(),
        type="button",
        class_name="bar__tema",
        data_tema="",
        aria_label="Cambiar entre modo claro y oscuro",
        title="Modo claro / oscuro",
    )
