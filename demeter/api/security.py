"""Seguridad de la API (A3, issue #21): contraseñas con bcrypt y tokens JWT.

- Las contraseñas nunca se guardan ni se comparan en claro: solo su huella bcrypt.
- El token JWT lleva el id del usuario (``sub``) y cuándo caduca (``exp``). No lleva el rol:
  el rol y si el usuario sigue activo se leen de la base de datos en cada petición, así que
  un cambio de rol o una baja tienen efecto al instante y no hay que esperar a que caduque.
"""

import os
import secrets
import warnings
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

ALGORITHM = "HS256"
# bcrypt solo lee los primeros 72 bytes de la contraseña; más largo se rechaza en vez de recortar.
MAX_PASSWORD_BYTES = 72
_PLACEHOLDER_SECRET = "cambia-esto-en-produccion"  # el valor de .env.example


def _load_secret() -> str:
    secret = os.environ.get("DEMETER_JWT_SECRET", "").strip()
    if secret == _PLACEHOLDER_SECRET:
        warnings.warn(
            "DEMETER_JWT_SECRET tiene el valor de ejemplo de .env.example: cámbialo por uno largo "
            "y aleatorio. Se usa un secreto temporal (los tokens caducan al reiniciar).",
            stacklevel=2,
        )
        secret = ""
    # Sin secreto configurado se genera uno al arrancar: es seguro, solo que los tokens
    # dejan de valer cuando se reinicia el servidor.
    return secret or secrets.token_urlsafe(48)


JWT_SECRET = _load_secret()
ACCESS_TOKEN_MINUTES = int(os.environ.get("DEMETER_JWT_MINUTES", "60"))


# ---------------------------------------------------------------- contraseñas


def hash_password(password: str) -> str:
    """Huella bcrypt de la contraseña (con sal propia dentro del resultado)."""
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        raise ValueError(f"La contraseña no puede pasar de {MAX_PASSWORD_BYTES} bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """``True`` si la contraseña corresponde a la huella. Nunca lanza error."""
    raw = password.encode("utf-8")
    if len(raw) > MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash.encode("ascii"))
    except ValueError:  # huella mal formada
        return False


# Huella de una contraseña inventada: sirve para gastar el mismo tiempo cuando el usuario no
# existe, y que no se pueda averiguar qué usuarios existen midiendo lo que tarda el login.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


# ---------------------------------------------------------------- tokens


def create_access_token(user_id: int, minutes: Optional[int] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES if minutes is None else minutes),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """Id de usuario del token, o ``None`` si está caducado, manipulado o mal formado."""
    try:
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]}
        )
        return int(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
