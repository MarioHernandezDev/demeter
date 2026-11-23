"""Quién es el usuario de cada petición (A3, issue #21).

``UserStore`` es la única puerta de la API a los usuarios guardados. Hoy hay una versión en
memoria con los tres usuarios de ejemplo; cuando la capa de consultas a la BD (B6, #13) esté
en ``main`` basta con escribir otra clase con los mismos dos métodos y devolverla desde
``get_user_store``. Nada más de este fichero cambia. Los tests hacen lo mismo con
``api.dependency_overrides[get_user_store]``.
"""

from dataclasses import dataclass
from typing import Optional, Protocol

from fastapi import Depends, Header, HTTPException

from demeter.api import sample_data as d
from demeter.api import schemas as s
from demeter.api.security import (
    DUMMY_HASH,
    decode_access_token,
    hash_password,
    verify_password,
)


@dataclass
class StoredUser:
    """Usuario tal y como se guarda: con la huella de la contraseña (que nunca sale de aquí)."""

    user: s.User
    password_hash: str


class UserStore(Protocol):
    def get_by_username(self, username: str) -> Optional[StoredUser]: ...

    def get_by_id(self, user_id: int) -> Optional[StoredUser]: ...


class DemoUserStore:
    """Usuarios de ejemplo (``admin``, ``tecnico``, ``lector``, contraseña ``demo1234``)."""

    def __init__(self) -> None:
        demo_hash = hash_password("demo1234")
        # Copias propias: cambiar a un usuario en un almacén no toca los datos de ejemplo.
        self._users = [StoredUser(u.model_copy(), demo_hash) for u in d.USERS.values()]

    def get_by_username(self, username: str) -> Optional[StoredUser]:
        return next((u for u in self._users if u.user.username == username), None)

    def get_by_id(self, user_id: int) -> Optional[StoredUser]:
        return next((u for u in self._users if u.user.id == user_id), None)


_demo_store = DemoUserStore()


def get_user_store() -> UserStore:
    return _demo_store


# ---------------------------------------------------------------- login


def authenticate(store: UserStore, username: str, password: str) -> Optional[s.User]:
    """El usuario si el nombre y la contraseña son correctos y está activo; si no, ``None``.

    Tarda lo mismo exista o no el usuario, y no distingue «no existe», «contraseña mala» y
    «dado de baja»: así no se puede averiguar qué usuarios hay.
    """
    stored = store.get_by_username(username)
    ok = verify_password(password, stored.password_hash if stored else DUMMY_HASH)
    if stored is None or not ok or not stored.user.is_active:
        return None
    return stored.user


# ---------------------------------------------------------------- dependencias de FastAPI


def current_user(
    authorization: Optional[str] = Header(default=None),
    store: UserStore = Depends(get_user_store),
) -> s.User:
    scheme, _, token = (authorization or "").partition(" ")
    user_id = decode_access_token(token.strip()) if scheme.lower() == "bearer" else None
    stored = store.get_by_id(user_id) if user_id is not None else None
    # Se vuelve a leer el usuario en cada petición: si lo dieron de baja o le cambiaron el
    # rol, vale desde ya, aunque el token siga sin caducar.
    if stored is None or not stored.user.is_active:
        raise HTTPException(
            401, "Falta el token o no es válido", headers={"WWW-Authenticate": "Bearer"}
        )
    return stored.user


def require(*roles: str):
    def check(user: s.User = Depends(current_user)) -> s.User:
        if user.role not in roles:
            raise HTTPException(403, "No tienes permiso para hacer esto")
        return user

    return check


ANY = Depends(current_user)
EDITOR = Depends(require("admin", "tecnico"))
ADMIN = Depends(require("admin"))
