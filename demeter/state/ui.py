"""Estado de la interfaz compartido por el layout (C2, issue #29).

Lo que no es de la sesión ni de una página concreta: por ahora, el contador de
alertas sin leer que se ve en la barra y en las pestañas.
"""

from __future__ import annotations

import reflex as rx


class UIState(rx.State):
    """Estado del layout."""

    # TODO(D3 · feature/alertas-pagina): rellenarlo con GET /api/dashboard
    # (``unread_alerts``) al cargar cada página privada y por WebSocket después.
    alertas_sin_leer: int = 0

    @rx.var
    def texto_alertas(self) -> str:
        """Lo que se pinta en la burbuja: a partir de 100 basta con «99+»."""
        n = self.alertas_sin_leer
        return "99+" if n > 99 else str(n)
