"""``/``: portada pública (C2, issue #29).

Decisión del equipo: ``/`` no redirige sin más; es la portada que ve el jurado y
cualquiera que llegue a la web. El botón «Ver el panel en vivo» lleva al panel si
hay sesión y al login si no (``AuthState.ir_al_panel``).

TODO(C2 · siguiente PR): portar la portada completa del prototipo (hero con la
montaña, secciones con scroll y Demetreo). Aquí va la versión mínima.
"""

import reflex as rx

from demeter.components.layout import layout
from demeter.state.auth import AuthState


@rx.page(route="/", title="Demeter · monitorización de parcelas")
def inicio() -> rx.Component:
    return layout(
        rx.el.section(
            rx.el.p("Agricultura de precisión · Granada", class_name="dm-etiqueta"),
            rx.el.h1(
                "Tu parcela, ",
                rx.el.em("en tiempo real", style={"font_family": "var(--dm-fuente-serif)", "font_weight": 400}),
                class_name="dm-titulo",
                style={"font_size": "clamp(40px, 8vw, 88px)", "line_height": "1", "margin": "14px 0 18px"},
            ),
            rx.el.p(
                "Temperatura, humedad del suelo, luz y humedad ambiental de cada parcela, "
                "con su histórico y un aviso en cuanto algo se sale de su rango.",
                class_name="dm-sub",
                style={"max_width": "560px", "font_size": "18px"},
            ),
            rx.el.div(
                rx.el.button("Ver el panel en vivo", on_click=AuthState.ir_al_panel, class_name="dm-boton"),
                rx.el.a("Cómo funciona", href="#como", class_name="dm-boton dm-boton--sec"),
                style={"display": "flex", "gap": "12px", "flex_wrap": "wrap"},
            ),
            style={"padding": "8vh 0 6vh"},
        ),
        rx.el.section(
            *[
                rx.el.div(
                    rx.el.p(n, class_name="dm-etiqueta"),
                    rx.el.h3(t, style={"margin": "8px 0 6px"}),
                    rx.el.p(d, style={"margin": 0, "color": "var(--dm-tinta-suave)"}),
                    class_name="dm-tarjeta",
                )
                for n, t, d in (
                    ("01", "Sensores", "Cada sensor envía su lectura a la API cada pocos segundos."),
                    ("02", "Histórico", "Todo se guarda: filtra por fechas y exporta lo que necesites."),
                    ("03", "Alertas", "Umbrales por sensor; si un valor se sale, te enteras al momento."),
                )
            ],
            id="como",
            class_name="dm-rejilla",
        ),
        publica=True,
    )
