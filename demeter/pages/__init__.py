"""Páginas de Demeter. Cada módulo registra su ruta con ``@rx.page``.

Importar este paquete (lo hace ``demeter/demeter.py``) basta para dar de alta todas,
incluida la 404.
"""

from demeter.pages import ajustes, alertas, dashboard, inicio, login, no_encontrada, parcelas

__all__ = ["ajustes", "alertas", "dashboard", "inicio", "login", "no_encontrada", "parcelas"]
