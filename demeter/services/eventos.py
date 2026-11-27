"""Aviso en directo de lo que pasa en una parcela (lecturas nuevas y alertas abiertas).

La ingesta ``publish``-a un evento cuando acaba de guardar una lectura; cada cliente conectado al
WebSocket de esa parcela tiene una cola (``subscribe``) y la recibe al instante, sin esperar a ningún
sondeo. Todo en memoria y en un solo proceso, como el resto de la app: no sobrevive a un reinicio
(un cliente que se reconecta no recibe lo que se perdió, pero sí el estado completo con el dashboard).

``publish`` se llama desde un hilo (las rutas síncronas de FastAPI) y las colas pertenecen al bucle
de eventos del servidor, así que se entrega con ``call_soon_threadsafe``. Cada cola tiene un tope: si
un cliente lento no las vacía, se descarta lo más antiguo en vez de crecer sin límite.
"""

from __future__ import annotations

import asyncio
import threading
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

QUEUE_SIZE = 200


@dataclass(eq=False)
class Subscription:
    parcel_id: int
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue

    def _put(self, event: dict[str, Any]) -> None:
        if self.queue.full():
            self.queue.get_nowait()  # el cliente va tarde: se tira lo más antiguo
        self.queue.put_nowait(event)


_lock = threading.Lock()
_subs: dict[int, set[Subscription]] = defaultdict(set)


def subscribe(parcel_id: int) -> Subscription:
    """Se apunta a los eventos de la parcela. Hay que llamarlo desde el bucle de eventos."""
    sub = Subscription(parcel_id, asyncio.get_running_loop(), asyncio.Queue(maxsize=QUEUE_SIZE))
    with _lock:
        _subs[parcel_id].add(sub)
    return sub


def unsubscribe(sub: Subscription) -> None:
    with _lock:
        _subs[sub.parcel_id].discard(sub)
        if not _subs[sub.parcel_id]:
            del _subs[sub.parcel_id]


def publish(parcel_id: int, event: dict[str, Any]) -> None:
    """Entrega el evento a todos los clientes de la parcela. No espera y no falla si no hay ninguno."""
    with _lock:
        targets = list(_subs.get(parcel_id, ()))
    for sub in targets:
        try:
            sub.loop.call_soon_threadsafe(sub._put, event)
        except RuntimeError:  # el bucle del cliente ya se cerró
            unsubscribe(sub)


def subscribers(parcel_id: int | None = None) -> int:
    """Cuántos clientes hay conectados (en una parcela, o en total). Para pruebas y diagnóstico."""
    with _lock:
        if parcel_id is not None:
            return len(_subs.get(parcel_id, ()))
        return sum(len(v) for v in _subs.values())
