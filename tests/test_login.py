"""Pruebas de la pantalla de login con Demetreo (C3, issue #30).

Comprueban lo que no se puede romper al retocar el diseño: los campos que lee
``AuthState.login``, el aviso de error accesible y que existen los archivos que carga.
"""

from pathlib import Path

import pytest

from demeter.pages import login as pagina

ASSETS = Path(__file__).resolve().parent.parent / "assets"


@pytest.fixture(scope="module")
def html() -> str:
    return str(pagina.login())


def test_los_campos_son_los_que_lee_auth_state(html):
    # AuthState.login lee form_data["username"] y form_data["password"].
    assert 'name:"username"' in html
    assert 'name:"password"' in html
    assert "current-password" in html


def test_el_error_se_anuncia_a_los_lectores_de_pantalla(html):
    assert "pl4-err" in html
    assert "alert" in html


def test_demetreo_y_el_fondo_son_decorativos(html):
    # El SVG, el bocadillo y el lienzo del fondo no deben leerse en voz alta.
    assert html.count("aria-hidden") >= 3


def test_existen_los_archivos_que_carga_la_pagina():
    for ruta in ("login/login.css", "login/fondo.js", "login/demetreo.js", "proto/proto.css"):
        assert (ASSETS / ruta).is_file(), ruta
    for n in range(1, pagina.FOTOGRAMAS + 1):
        assert (ASSETS / "login" / "img" / f"demetreo-{n}.webp").is_file()


def test_el_svg_tiene_las_piezas_que_mueve_el_script():
    svg = pagina.SVG_DEMETREO.read_text(encoding="utf-8")
    js = (ASSETS / "login" / "demetreo.js").read_text(encoding="utf-8")
    for pieza in ("av-svg", "av-bounce", "av-mouth", "pupil", "eyebrow-left", "eyebrow-right"):
        assert pieza in svg, pieza
        assert pieza in js, pieza
    # Las manos las mueve el CSS con las clases que pone el script.
    css = (ASSETS / "login" / "login.css").read_text(encoding="utf-8")
    assert "avocado-arm-left" in svg and "avocado-state-cover" in css and "avocado-state-cover" in js
