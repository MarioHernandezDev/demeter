"""Pruebas del layout, el tema y las rutas (C2, issue #29)."""

import pytest
import reflex as rx

from demeter import theme
from demeter.components import prototipo
from demeter.components.layout import SECCIONES, layout
from demeter.state.auth import HOME_AFTER_LOGIN, LOGIN_ROUTE, PUBLIC_ROUTES, destino_panel

PRIVADAS = ["dashboard", "parcelas", "alertas", "ajustes"]
PUBLICAS = ["inicio", "login", "no_encontrada"]


@pytest.fixture(scope="module")
def paginas():
    import demeter.pages as p

    return {n: str(getattr(getattr(p, n), n)()) for n in PRIVADAS + PUBLICAS}


# ---------------------------------------------------------------- tema


def test_cada_color_tiene_su_variable_css():
    css = theme.css_global()
    for nombre, valor in theme.COLORES.items():
        assert f"--dm-{nombre.replace('_', '-')}: {valor};" in css


def test_la_paleta_coincide_con_la_del_prototipo():
    # Las hojas del prototipo y theme.py tienen que decir lo mismo hasta que se unifiquen.
    proto = (prototipo.PLANTILLAS.parent.parent.parent / "assets" / "proto" / "proto.css").read_text()
    app = (prototipo.PLANTILLAS.parent.parent.parent / "assets" / "proto" / "app.css").read_text()
    assert f"--ink: {theme.COLORES['tinta']}" in proto
    for clave, var in (("acento", "--warn"), ("tinta_suave", "--muted"), ("papel", "--paper"), ("sin_senal", "--off")):
        assert f"{var}: {theme.COLORES[clave]}" in app


# ---------------------------------------------------------------- layout


def test_todas_las_paginas_usan_layout(paginas):
    for nombre, html in paginas.items():
        assert "dm-shell" in html, f"{nombre} no usa layout()"


def test_las_privadas_tienen_navegacion_y_pestanas(paginas):
    for nombre in PRIVADAS:
        html = paginas[nombre]
        assert "bar__nav" in html and '"tabs"' in html, nombre
        for s in SECCIONES:
            assert s.ruta in html


def test_las_publicas_no_tienen_pestanas(paginas):
    for nombre in PUBLICAS:
        assert '"tabs"' not in paginas[nombre], nombre


def test_la_seccion_activa_lleva_aria_current():
    html = str(layout(rx.el.p("x"), activa="/alertas"))
    # Dos enlaces activos: el de la barra y el de la pestaña móvil.
    assert html.count('"page"') == 2


def test_cada_pagina_del_prototipo_tiene_su_plantilla():
    for nombre in ("inicio", "panel", "parcelas", "alertas", "ajustes", "no_encontrada"):
        html = prototipo.plantilla(nombre)
        assert "<main" in html
        # Los enlaces ya apuntan a las rutas de Reflex, no a los .html del prototipo.
        assert ".html" not in html


def test_contenido_con_centro_mete_el_componente_en_el_marcador(monkeypatch):
    monkeypatch.setattr(prototipo, "plantilla", lambda _: '<main id="top"><p>antes</p><!-- @x --><p>despues</p></main>')
    html = str(prototipo.contenido_con_centro("x", "<!-- @x -->", rx.el.span("centro"), ""))
    assert html.index("antes") < html.index("centro") < html.index("despues")
    assert "@x" not in html


def test_contenido_con_centro_avisa_si_falta_el_marcador_o_el_main(monkeypatch):
    monkeypatch.setattr(prototipo, "plantilla", lambda _: '<main id="top"><p>sin marcador</p></main>')
    with pytest.raises(ValueError, match="marcador"):
        prototipo.contenido_con_centro("x", "<!-- @x -->", rx.el.span(), "")
    monkeypatch.setattr(prototipo, "plantilla", lambda _: "<div><!-- @x --></div>")
    with pytest.raises(ValueError, match="main"):
        prototipo.contenido_con_centro("x", "<!-- @x -->", rx.el.span(), "")


def test_la_portada_lleva_la_cabina_3d_y_el_gemelo(paginas):
    from demeter.components.cabina3d import mundos
    from demeter.pages.inicio import MARCADOR_MUNDOS

    assert MARCADOR_MUNDOS in prototipo.plantilla("inicio")
    html = paginas["inicio"]
    assert "Cabina3D" in html and "data-ss-card" in html
    # los scripts van en el on_mount, que no sale en el HTML: se miran en el código de la página
    import inspect

    import demeter.pages.inicio as inicio

    assert '"scroll-split.js"' in inspect.getsource(inicio)
    assets = prototipo.PLANTILLAS.parent.parent.parent / "assets"
    ids = [m["id"] for m in mundos()]
    assert ids == ["medir", "avisar", "regar", "gemelo"]
    for m in mundos():
        assert (assets / m["img"].lstrip("/")).is_file(), m["img"]


def test_ningun_script_de_la_portada_tira_de_cdn_para_three():
    proto = prototipo.PLANTILLAS.parent.parent.parent / "assets" / "proto"
    for js in ("scroll-split.js", "intro.js", "twin.js"):
        assert "cdn.jsdelivr.net/npm/three" not in (proto / js).read_text(encoding="utf-8"), js


# ---------------------------------------------------------------- rutas


def test_la_app_registra_todas_las_rutas():
    import demeter.demeter  # noqa: F401  (importa las páginas igual que «reflex run»)
    from reflex_base.registry import RegistrationContext

    rutas = {kw.get("route") for _, kw in RegistrationContext.ensure_context().decorated_pages}
    assert {"/", "/login", "/dashboard", "/parcelas", "/alertas", "/ajustes", "404"} <= rutas


def test_solo_inicio_y_login_son_publicas():
    assert PUBLIC_ROUTES == {"/", LOGIN_ROUTE}


@pytest.mark.parametrize(
    ("con_sesion", "esperado"),
    [(True, HOME_AFTER_LOGIN), (False, f"{LOGIN_ROUTE}?next={HOME_AFTER_LOGIN}")],
)
def test_ver_el_panel_lleva_al_panel_o_al_login(con_sesion, esperado):
    assert destino_panel(con_sesion) == esperado
