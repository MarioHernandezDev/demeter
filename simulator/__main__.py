"""Bucle del simulador y opciones de la línea de órdenes (B4, issue #15).

    python -m simulator --help
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from demeter.db.seed import SENSORS
from simulator.cliente import Respuesta, enviar
from simulator.modelos import Modelo, crear_modelo

# ---------------------------------------------------------------------------------------
# Qué sensores se simulan
#
# Solo los del seed: la lista sale de ``demeter.db.seed.SENSORS``, así que si el seed cambia, el
# simulador lo sigue sin tocar nada. Un sensor que no está en el seed (p. ej. uno real de una
# placa Arduino) NUNCA se simula, aunque esté en la base de datos: así no se mezclan sus datos.
# ---------------------------------------------------------------------------------------


def crear_modelos(codigos: list[str] | None = None, semilla: int | None = None) -> list[Modelo]:
    """Un modelo por sensor del seed. Con ``codigos``, solo esos (``ValueError`` si alguno no es
    del seed, para que una errata no se pase por alto)."""
    del_seed = {codigo: tipo for codigo, _finca, tipo, _desc in SENSORS}
    if codigos:
        desconocidos = sorted(set(codigos) - set(del_seed))
        if desconocidos:
            raise ValueError(f"Estos sensores no son del seed: {', '.join(desconocidos)}")
        elegidos = [c for c in del_seed if c in codigos]  # en el orden del seed
    else:
        elegidos = list(del_seed)
    return [crear_modelo(codigo, del_seed[codigo], semilla) for codigo in elegidos]


# ---------------------------------------------------------------------------------------
# El bucle
# ---------------------------------------------------------------------------------------


@dataclass
class Resumen:
    """Lo que ha pasado en una ronda (una lectura por sensor)."""

    enviadas: int = 0
    repetidas: int = 0
    errores: dict[str, str] = field(default_factory=dict)  # código -> por qué falló


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def ejecutar(
    modelos: list[Modelo],
    mandar: Callable[[str, datetime, float], Respuesta],
    rondas: int = 0,
    intervalo: float = 60.0,
    velocidad: float = 1.0,
    reloj: Callable[[], datetime] = ahora_utc,
    dormir: Callable[[float], None] = time.sleep,
    avisar: Callable[[str], None] = print,
) -> int:
    """Manda una lectura por sensor cada ``intervalo`` segundos. Devuelve el código de salida.

    - ``rondas``: cuántas rondas; 0 = sin fin (hasta Ctrl+C).
    - ``velocidad``: cuánto tiempo SIMULADO pasa por cada segundo real. Con 60, cada minuto real
      avanza una hora el ciclo del día. Las lecturas se envían siempre con la hora REAL, porque la
      API rechaza horas de más de 5 min en el futuro; lo que se acelera son los valores.
    - ``mandar``, ``reloj``, ``dormir`` y ``avisar`` se pueden cambiar: las pruebas los sustituyen
      para no usar la red ni esperar de verdad.

    Qué hace ante cada fallo:
    - API apagada o inalcanzable: avisa y lo reintenta en la ronda siguiente.
    - 401 (clave incorrecta): para, porque todas las demás fallarían igual.
    - 404 (sensor que no está en la base de datos): avisa una vez y deja de simular ese sensor.
    - Cualquier otro error: avisa y sigue.
    """
    activos = list(modelos)
    inicio = reloj()
    instante_simulado = inicio
    paso = timedelta(seconds=intervalo * velocidad)
    ronda = 0
    while activos and (rondas == 0 or ronda < rondas):
        ronda += 1
        empieza = reloj()
        resumen = Resumen()
        for modelo in list(activos):
            valor = modelo.avanzar(instante_simulado, paso)
            respuesta = mandar(modelo.codigo, empieza, valor)
            if respuesta.ok:
                resumen.enviadas += 1
                resumen.repetidas += respuesta.repetida
            elif respuesta.estado == 401:
                avisar("La API rechaza la clave (X-API-Key). Revisa --api-key o DEMETER_INGEST_KEY.")
                return 2
            elif respuesta.estado == 404:
                avisar(f"El sensor {modelo.codigo} no existe en la base de datos: se deja de simular.")
                activos.remove(modelo)
            else:
                resumen.errores[modelo.codigo] = respuesta.detalle or f"HTTP {respuesta.estado}"
        avisar(_linea(ronda, empieza, instante_simulado, resumen, velocidad))
        instante_simulado += paso
        if rondas == 0 or ronda < rondas:
            # Se descuenta lo que ha tardado la ronda, para no ir acumulando retraso.
            transcurrido = (reloj() - empieza).total_seconds()
            dormir(max(0.0, intervalo - transcurrido))
    if not activos:
        avisar("No queda ningún sensor que simular.")
        return 1
    return 0


def _linea(ronda: int, real: datetime, simulado: datetime, r: Resumen, velocidad: float) -> str:
    texto = f"[{real:%H:%M:%S}] ronda {ronda}: {r.enviadas} enviadas"
    if velocidad != 1:
        texto += f" (hora simulada {simulado:%H:%M})"
    if r.repetidas:
        texto += f", {r.repetidas} repetidas"
    if r.errores:
        motivos = sorted(set(r.errores.values()))
        texto += f", {len(r.errores)} con error: {'; '.join(motivos)}"
    return texto


# ---------------------------------------------------------------------------------------
# Línea de órdenes
# ---------------------------------------------------------------------------------------


def _opciones(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m simulator",
        description="Manda lecturas inventadas de los sensores del seed a la API de Demeter.",
    )
    p.add_argument("--api-url", default=os.environ.get("DEMETER_API_URL", "http://127.0.0.1:8000"),
                   help="dirección de la API (o DEMETER_API_URL). Por defecto: %(default)s")
    p.add_argument("--api-key", default=os.environ.get("DEMETER_INGEST_KEY", "demo-ingest-key"),
                   help="clave de ingesta, la misma que usa la API (o DEMETER_INGEST_KEY)")
    p.add_argument("--intervalo", type=float, default=60.0,
                   help="segundos entre rondas. Por defecto: %(default)s")
    p.add_argument("--velocidad", type=float, default=1.0,
                   help="tiempo simulado por cada segundo real. Por defecto: %(default)s")
    p.add_argument("--rapido", action="store_true",
                   help="atajo para la demo: --intervalo 2 --velocidad 60 (un día en 24 min)")
    p.add_argument("--sensores", help="solo estos sensores, separados por comas (p. ej. t001,h001)")
    p.add_argument("--rondas", type=int, default=0, help="cuántas rondas; 0 = sin fin (Ctrl+C)")
    p.add_argument("--semilla", type=int, help="para que la simulación salga igual cada vez")
    opciones = p.parse_args(argv)
    if opciones.rapido:
        opciones.intervalo, opciones.velocidad = 2.0, 60.0
    if opciones.intervalo <= 0 or opciones.velocidad <= 0:
        p.error("--intervalo y --velocidad tienen que ser mayores que 0")
    if opciones.rondas < 0:
        p.error("--rondas no puede ser negativo")
    return opciones


def main(argv: list[str] | None = None) -> int:
    opciones = _opciones(argv)
    codigos = [c.strip() for c in opciones.sensores.split(",")] if opciones.sensores else None
    try:
        modelos = crear_modelos(codigos, opciones.semilla)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    def mandar(codigo: str, instante: datetime, valor: float) -> Respuesta:
        return enviar(opciones.api_url, opciones.api_key, codigo, instante, valor)

    print(
        f"Simulando {len(modelos)} sensores contra {opciones.api_url}, una ronda cada "
        f"{opciones.intervalo:g} s (velocidad x{opciones.velocidad:g}). Ctrl+C para parar."
    )
    try:
        return ejecutar(modelos, mandar, opciones.rondas, opciones.intervalo, opciones.velocidad)
    except KeyboardInterrupt:
        print("\nSimulador parado.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
