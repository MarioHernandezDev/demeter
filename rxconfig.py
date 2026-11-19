"""Configuración de Reflex. Arranque en local: ``reflex run`` (ver README)."""

import os

import reflex as rx
from reflex.plugins.sitemap import SitemapPlugin

config = rx.Config(
    app_name="demeter",
    # Base de datos: SQLite en local por defecto. Para otro motor basta con
    # definir DEMETER_DATABASE_URL (ya está en .env.example), sin tocar código.
    db_url=os.environ.get("DEMETER_DATABASE_URL", "sqlite:///data/demeter.db"),
    # El sitemap no hace falta: es una app privada salvo la portada.
    disable_plugins=[SitemapPlugin],
)