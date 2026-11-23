"""Sesión del usuario: esqueleto de ``AuthState`` (C1, issue #28).

Qué hay ya:
- El token y el usuario se guardan en el LocalStorage del navegador, así que la
  sesión sobrevive a recargar la página y se comparte entre pestañas.
- ``logout`` y ``require_login`` (la protección de páginas) ya funcionan.
- ``AuthState.headers`` da la cabecera ``Authorization`` para llamar a la API.

- ``login`` llama a ``POST /api/auth/login`` (C3, issue #30). Hoy responde el
  contrato de la API con usuarios de ejemplo (``admin``/``tecnico``/``lector``,
  contraseña ``demo1234``); cuando A3 una el login con JWT la respuesta es la misma.

Qué falta:
- Comprobar que el token sigue siendo válido (si caduca, la API responde 401 y hay
  que llamar a ``logout``).

Cómo se usa en una página protegida::

    @rx.page(route="/dashboard", on_load=AuthState.require_login)
    def dashboard() -> rx.Component: ...
"""

from __future__ import annotations

import httpx
import reflex as rx

from demeter.state.types import LoginResponse, Role

# Rutas que usa la sesión. Si C2 cambia alguna, se cambia solo aquí.
LOGIN_ROUTE = "/login"
HOME_AFTER_LOGIN = "/dashboard"
# Páginas que se ven sin sesión. Todo lo demás exige haber entrado.
PUBLIC_ROUTES = frozenset({"/", LOGIN_ROUTE})


def destino_panel(con_sesion: bool) -> str:
    """A dónde lleva «Ver el panel» desde la portada: al panel, o al login y luego al panel."""
    return HOME_AFTER_LOGIN if con_sesion else f"{LOGIN_ROUTE}?next={HOME_AFTER_LOGIN}"


class AuthState(rx.State):
    """Estado de la sesión, compartido por todas las páginas."""

    # Guardados en el navegador (LocalStorage). ``sync=True`` mantiene igual todas
    # las pestañas abiertas: cerrar sesión en una la cierra en las demás.
    token: str = rx.LocalStorage("", name="demeter_token", sync=True)
    username: str = rx.LocalStorage("", name="demeter_user", sync=True)
    role: str = rx.LocalStorage("", name="demeter_role", sync=True)

    # Estado del formulario de login (no se guarda).
    error: str = ""
    loading: bool = False

    @rx.var
    def is_authenticated(self) -> bool:
        """Hay sesión si hay token. Que el token sea válido lo decide la API."""
        return bool(self.token)

    @rx.var
    def inicial(self) -> str:
        """Letra del avatar de la barra («T» de tecnico)."""
        return (self.username[:1] or "?").upper()

    @rx.var
    def is_admin(self) -> bool:
        """Solo el administrador puede editar umbrales (pantalla 06)."""
        return self.role == Role.ADMIN.value

    @rx.var
    def headers(self) -> dict[str, str]:
        """Cabeceras para las peticiones a la API protegida."""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @rx.event
    def require_login(self):
        """``on_load`` de las páginas privadas: sin sesión, al login.

        Guarda la página pedida en ``?next=`` para volver a ella después de entrar.
        """
        if self.is_authenticated:
            return None
        here = self.router.url.path or HOME_AFTER_LOGIN
        if here in PUBLIC_ROUTES:
            return None
        return rx.redirect(f"{LOGIN_ROUTE}?next={here}")

    @rx.event
    def ir_al_panel(self):
        """Botón «Ver el panel en vivo» de la portada (C2): al panel o al login."""
        return rx.redirect(destino_panel(self.is_authenticated))

    @rx.event
    def redirect_if_logged_in(self):
        """``on_load`` de ``/login``: si ya hay sesión, no tiene sentido volver a entrar."""
        if self.is_authenticated:
            return rx.redirect(self._next_route())
        return None

    @rx.event
    async def login(self, form_data: dict):
        """Envío del formulario de login (``rx.form(on_submit=AuthState.login)``).

        Espera los campos ``username`` y ``password``.
        """
        username = (form_data.get("username") or "").strip()
        password = form_data.get("password") or ""
        if not username or not password:
            self.error = "Escribe tu usuario y tu contraseña."
            return

        self.error = ""
        self.loading = True
        yield  # pinta «Entrando…» antes de esperar a la API

        # El backend de Reflex llama a su propia API (misma app, /api montada en él).
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{rx.config.get_config().api_url}/api/auth/login",
                    json={"username": username, "password": password},
                )
        except httpx.HTTPError:
            self.loading = False
            self.error = "No se puede conectar con el servidor. Inténtalo de nuevo."
            return

        if resp.status_code == 401:
            self.loading = False
            self.error = "Usuario o contraseña incorrectos."
            return
        if resp.status_code != 200:
            self.loading = False
            self.error = "El servidor no ha podido iniciar la sesión. Inténtalo de nuevo."
            return

        r = LoginResponse.from_api(resp.json())
        self._open_session(r.access_token, r.user.username if r.user else username, r.user.role if r.user else "")
        yield rx.redirect(self._next_route())

    @rx.event
    def logout(self):
        """Cierra la sesión en este navegador y vuelve al login."""
        self.token = ""
        self.username = ""
        self.role = ""
        self.error = ""
        return rx.redirect(LOGIN_ROUTE)

    def _open_session(self, token: str, username: str, role: str) -> None:
        """Guarda la sesión tras un login correcto (lo usará C3)."""
        self.token = token
        self.username = username
        self.role = role or Role.TECNICO.value
        self.loading = False
        self.error = ""

    def _next_route(self) -> str:
        """A dónde ir después de entrar: ``?next=`` si es una ruta interna, si no el dashboard."""
        nxt = self.router.url.query_parameters.get("next", "")
        if nxt.startswith("/") and not nxt.startswith("//") and nxt not in PUBLIC_ROUTES:
            return nxt
        return HOME_AFTER_LOGIN
