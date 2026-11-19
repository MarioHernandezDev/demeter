"""Pruebas del layout, el tema y las rutas (C2, issue #29)."""

import re

import pytest
import reflex as rx

from demeter import theme
from demeter.components.layout import SECCIONES, layout
from demeter.state.auth import HOME_AFTER_LOGIN, LOGIN_ROUTE, PUBLIC_ROUTES, destino_panel

PRIVADAS = ["dashboard", "parcelas", "alertas", "ajustes"]
PUBLICAS = ["inicio", "login"]


def _html(componente: rx.Component) -> str:
    """Representación en texto del árbol del componente (lo que Reflex compilaría)."""
    return str(componente)


@pytest.fixture(scope="module")
def paginas():
    import demeter.pages as p

    return {n: getattr(getattr(p, n), n)() for n in PRIVADAS + PUBLICAS}


# ---------------------------------------------------------------- tema


def test_cada_color_tiene_su_variable_css():
    css = theme.css_global()
    for nombre, valor in theme.COLORES.items():
        assert f"--dm-{nombre.replace('_', '-')}: {valor};" in css


def test_el_responsive_corta_donde_dice_el_tema():
    assert f"@media (max-width: {theme.CORTE_MOVIL_PX}px)" in theme.css_global()


def test_el_css_no_lleva_colores_sueltos_fuera_de_las_variables():
    # Fuera del bloque :root solo se admiten blanco y transparencias: el resto debe ir por --dm-*.
    cuerpo = theme.css_global().split("}", 1)[1]
    sueltos = set(re.findall(r"#[0-9a-fA-F]{6}\b", cuerpo))
    assert sueltos == set()


# ---------------------------------------------------------------- layout


def test_todas_las_paginas_usan_layout(paginas):
    for nombre, comp in paginas.items():
        assert "dm-shell" in _html(comp), f"/{nombre} no usa layout()"


def test_las_privadas_tienen_navegacion_y_pestanas(paginas):
    for nombre in PRIVADAS:
        html = _html(paginas[nombre])
        assert "dm-nav" in html and "dm-pestanas" in html, nombre
        for s in SECCIONES:
            assert s.ruta in html


def test_las_publicas_no_muestran_la_navegacion_de_la_app(paginas):
    for nombre in PUBLICAS:
        html = _html(paginas[nombre])
        assert "dm-pestanas" not in html and "dm-nav" not in html, nombre


def test_la_seccion_activa_lleva_aria_current():
    html = _html(layout(rx.el.p("x"), activa="/alertas"))
    # Dos enlaces activos: el de la barra y el de la pestaña móvil.
    assert html.count('"page"') == 2


def test_hay_cuatro_secciones_para_las_pestanas_moviles():
    assert [s.ruta for s in SECCIONES] == ["/dashboard", "/parcelas", "/alertas", "/ajustes"]
    assert "repeat(4, 1fr)" in theme.css_global()


# ---------------------------------------------------------------- rutas


def test_la_app_registra_las_seis_rutas():
    import demeter.demeter  # noqa: F401  (importa las páginas igual que «reflex run»)
    from reflex_base.registry import RegistrationContext

    rutas = {kw.get("route") for _, kw in RegistrationContext.ensure_context().decorated_pages}
    assert {"/", "/login", "/dashboard", "/parcelas", "/alertas", "/ajustes"} <= rutas


def test_solo_inicio_y_login_son_publicas():
    assert PUBLIC_ROUTES == {"/", LOGIN_ROUTE}


@pytest.mark.parametrize(
    ("con_sesion", "esperado"),
    [(True, HOME_AFTER_LOGIN), (False, f"{LOGIN_ROUTE}?next={HOME_AFTER_LOGIN}")],
)
def test_ver_el_panel_lleva_al_panel_o_al_login(con_sesion, esperado):
    assert destino_panel(con_sesion) == esperado
