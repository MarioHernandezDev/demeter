"""Estado de la interfaz compartido por el layout (C2, issue #29).

Lo que no es de la sesión ni de una página concreta: por ahora, el contador de
alertas sin leer que se ve en la barra y en las pestañas.
"""

from __future__ import annotations

import reflex as rx


class UIState(rx.State):
    """Estado del layout."""

    # Mientras tanto vale 2, las alertas sin leer de los datos de ejemplo del prototipo.
    # TODO(D3 · feature/alertas-pagina): rellenarlo con GET /api/dashboard
    # (``unread_alerts``) al cargar cada página privada y por WebSocket después.
    alertas_sin_leer: int = 2

    @rx.var
    def texto_alertas(self) -> str:
        """Lo que se pinta en la burbuja: nada si no hay, y «99+» a partir de 100."""
        n = self.alertas_sin_leer
        return "" if n <= 0 else "99+" if n > 99 else str(n)
