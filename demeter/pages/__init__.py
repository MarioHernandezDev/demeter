"""Páginas de Demeter. Cada módulo registra su ruta con ``@rx.page``.

Importar este paquete (lo hace ``demeter/demeter.py``) basta para dar de alta todas.
"""

from demeter.pages import ajustes, alertas, dashboard, inicio, login, parcelas

__all__ = ["ajustes", "alertas", "dashboard", "inicio", "login", "parcelas"]
