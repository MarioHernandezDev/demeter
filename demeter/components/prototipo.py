"""Contenido del prototipo «Demeter web completa con Demetreo griego» dentro de Reflex.

Mientras cada rama no rehaga su pantalla con componentes Reflex y datos de la API,
la página muestra la maqueta del prototipo tal cual:

- El HTML de cada pantalla está en ``demeter/pages/plantillas/<nombre>.html`` (solo
  el contenido: la barra y las pestañas las pone ``layout()`` en Reflex).
- Estilos, scripts e imágenes están en ``assets/proto/``. Los datos que pintan los
  scripts son de ejemplo (``app.js``) y no salen de la API.

Cuando una rama sustituya su plantilla (p. ej. ``feature/dashboard-graficas`` en el
panel), borra el ``.html`` y deja de llamar a :func:`contenido`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import reflex as rx

from demeter import theme

PLANTILLAS = Path(__file__).resolve().parent.parent / "pages" / "plantillas"


@lru_cache(maxsize=None)
def plantilla(nombre: str) -> str:
    """HTML de una pantalla del prototipo (se lee una vez al compilar)."""
    return (PLANTILLAS / f"{nombre}.html").read_text(encoding="utf-8")


def _arranque(clase_body: str, niebla: bool, scripts: tuple[str, ...]) -> str:
    """JavaScript que prepara la página y carga los scripts del prototipo.

    - Pone en ``<body>`` y ``<html>`` las clases que esperan las hojas del prototipo.
    - Carga cada script como módulo y en orden. El ``?v=`` fuerza a ejecutarlo de
      nuevo si Reflex cambia de página sin recargar (p. ej. tras el login).
    - Mientras cargan, ``<html data-dm-scripts>``: la pantalla de carga del aguacate
      (``assets/proto/carga.js``) espera a que se quite.
    """
    return (
        "(async () => {"
        "const raiz = document.documentElement; raiz.setAttribute('data-dm-scripts', '');"
        "try {"
        f"document.body.className = {json.dumps(clase_body)};"
        f"raiz.classList.toggle('is-fog', {json.dumps(niebla)});"
        "const v = Date.now();"
        f"for (const s of {json.dumps(list(scripts))}) {{ await import(`/proto/${{s}}?v=${{v}}`); }}"
        "} finally { raiz.removeAttribute('data-dm-scripts'); }"
        "})();"
    )


def hojas(app: bool = True) -> list[rx.Component]:
    """``<link>`` a las hojas del prototipo (la portada no usa ``app.css``)."""
    return [rx.el.link(rel="stylesheet", href=h) for h in (theme.HOJAS_APP if app else theme.HOJAS_PORTADA)]


def preparar(clase_body: str, niebla: bool = True, scripts: tuple[str, ...] = ("mascota.js",)) -> rx.Component:
    """Elemento invisible que, al montarse, ejecuta :func:`_arranque`."""
    return rx.el.div(
        hidden=True,
        on_mount=rx.call_script(_arranque(clase_body, niebla, scripts)),
    )


def contenido(
    nombre: str,
    clase_body: str,
    niebla: bool = True,
    scripts: tuple[str, ...] = ("app.js", "mascota.js"),
    app: bool = True,
) -> rx.Component:
    """La plantilla ``nombre`` con sus hojas y sus scripts."""
    return rx.fragment(
        *hojas(app),
        rx.html(plantilla(nombre), class_name="proto"),
        preparar(clase_body, niebla, scripts),
    )
