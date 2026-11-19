"""Configuración de Reflex. Arranque en local: ``reflex run`` (ver README)."""

import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="demeter",
    # El sitemap no hace falta: es una app privada salvo la portada.
    disable_plugins=[SitemapPlugin],
)
