"""Punto de entrada de la app Reflex (``reflex run`` lo carga según ``rxconfig.py``).

- La interfaz: las páginas de ``demeter/pages`` con el tema de ``demeter/theme.py``.
- La API REST: la app FastAPI de ``demeter/api`` se monta en el mismo servidor con
  ``api_transformer``, así que ``/api/...`` y ``/docs`` salen del backend de Reflex
  (puerto 8000 por defecto).
"""

import reflex as rx

import demeter.pages  # noqa: F401  (registra todas las rutas con @rx.page)
from demeter.api.app import api
from demeter.theme import GOOGLE_FONTS, css_global

app = rx.App(
    api_transformer=api,
    stylesheets=[GOOGLE_FONTS],
    head_components=[rx.el.style(css_global())],
    html_lang="es",
)
