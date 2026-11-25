"""Cómo cambia cada magnitud con el tiempo (B4, issue #15).

Cada sensor tiene su propio modelo, con su propio estado. En cada paso se le dice qué hora es
(``instante``) y cuánto tiempo ha pasado desde el paso anterior (``paso``), y devuelve el valor
que mediría ahora.

Los valores son los de la Costa Tropical en otoño y están pensados para quedarse DENTRO de los
umbrales del seed: en funcionamiento normal no deben saltar alertas. Las situaciones que sí las
provocan (helada, ola de calor, fallo de riego) son los escenarios de la #16.

Sobre la hora: se usa la hora UTC como si fuera la hora solar. En Almuñécar el mediodía solar cae
hacia las 12:15 UTC, así que el error es de un cuarto de hora: suficiente para una simulación.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta


def hora_del_dia(instante: datetime) -> float:
    """Hora del día en decimal: las 15:30 son 15.5."""
    return instante.hour + instante.minute / 60 + instante.second / 3600


def ciclo_diario(instante: datetime, hora_maxima: float) -> float:
    """Onda del día entre -1 y 1 que vale 1 a ``hora_maxima`` y -1 doce horas antes o después."""
    return math.cos(2 * math.pi * (hora_del_dia(instante) - hora_maxima) / 24)


def sol(instante: datetime) -> float:
    """Cuánto sol hay, de 0 (noche) a 1 (mediodía). Día de otoño: de 7:00 a 18:00."""
    amanecer, anochecer = 7.0, 18.0
    hora = hora_del_dia(instante)
    if not amanecer < hora < anochecer:
        return 0.0
    return math.sin(math.pi * (hora - amanecer) / (anochecer - amanecer))


def _limitar(valor: float, minimo: float, maximo: float) -> float:
    return max(minimo, min(maximo, valor))


class Modelo:
    """Base común. Cada sensor tiene su generador aleatorio, creado a partir de su código: así,
    con la misma semilla, la simulación sale igual cada vez (útil para las pruebas y para repetir
    una demo) y dos sensores del mismo tipo no dan exactamente los mismos valores."""

    def __init__(self, codigo: str, semilla: int | None = None) -> None:
        self.codigo = codigo
        self.azar = random.Random(f"{semilla}-{codigo}" if semilla is not None else None)
        # Cada sensor está en un sitio un poco distinto: le damos un pequeño desvío propio.
        self.desvio = self.azar.uniform(-1, 1)

    def ruido(self, amplitud: float) -> float:
        """Pequeño error de medida, como el de un sensor real."""
        return self.azar.gauss(0, amplitud)

    def avanzar(self, instante: datetime, paso: timedelta) -> float:  # pragma: no cover
        raise NotImplementedError


class Temperatura(Modelo):
    """Mínima de madrugada (~12 ºC) y máxima a media tarde (~24 ºC). Umbrales del seed: 8 y 35."""

    def avanzar(self, instante: datetime, paso: timedelta) -> float:
        media = 18 + self.desvio
        return round(media + 6 * ciclo_diario(instante, hora_maxima=15) + self.ruido(0.3), 1)


class HumedadAmbiente(Modelo):
    """Al revés que la temperatura: alta de madrugada (~74 %) y baja por la tarde (~50 %).
    Umbrales del seed: 30 y 85. Se deja margen por arriba: el ruido no debe rozar el 85 y abrir
    una alerta falsa en mitad de una demo."""

    def avanzar(self, instante: datetime, paso: timedelta) -> float:
        media = 62 + 2 * self.desvio
        valor = media - 12 * ciclo_diario(instante, hora_maxima=15) + self.ruido(1.2)
        return round(_limitar(valor, 0, 100), 1)


class Luminosidad(Modelo):
    """0 de noche y hasta ~70 klx a mediodía, con nubes que van y vienen. Umbral del seed: 100.

    Las nubes son un "paseo aleatorio": cada paso se mueven un poco desde donde estaban, en vez de
    sortearse de cero. Así no pasa de sol pleno a nublado de un minuto al siguiente.
    """

    def __init__(self, codigo: str, semilla: int | None = None) -> None:
        super().__init__(codigo, semilla)
        self.nubes = 0.9  # 1 = cielo despejado

    def avanzar(self, instante: datetime, paso: timedelta) -> float:
        horas = paso.total_seconds() / 3600
        self.nubes = _limitar(self.nubes + self.azar.gauss(0, 0.05 * math.sqrt(horas)), 0.6, 1.0)
        valor = 70 * sol(instante) * self.nubes
        return round(max(0.0, valor + (self.ruido(0.5) if valor > 0 else 0)), 1)


class HumedadSuelo(Modelo):
    """Baja poco a poco (más rápido con sol, porque la planta transpira) y sube de golpe al regar.

    Se riega solo cuando baja del 32 %, y el riego la sube al ~52 %. Umbrales del seed: 25 y 60,
    así que en funcionamiento normal no salta ninguna alerta. Si el riego fallara, bajaría hasta
    cruzar el 25 %: es el escenario "fallo de riego" de la #16.
    """

    UMBRAL_RIEGO = 32.0
    DESPUES_DE_REGAR = 52.0

    def __init__(self, codigo: str, semilla: int | None = None) -> None:
        super().__init__(codigo, semilla)
        self.humedad = self.azar.uniform(38, 50)
        self.riega = True  # la #16 lo pondrá a False para simular un fallo de riego

    def avanzar(self, instante: datetime, paso: timedelta) -> float:
        horas = paso.total_seconds() / 3600
        # Pierde ~0,25 %/h de noche y ~0,7 %/h a pleno sol.
        self.humedad -= (0.25 + 0.45 * sol(instante)) * horas
        if self.riega and self.humedad < self.UMBRAL_RIEGO:
            self.humedad = self.DESPUES_DE_REGAR + self.azar.uniform(-2, 2)
        self.humedad = _limitar(self.humedad, 0, 100)
        return round(_limitar(self.humedad + self.ruido(0.2), 0, 100), 1)


class NivelDeposito(Modelo):
    """Baja despacio con el uso (~0,3 %/h) y se rellena al llegar al 35 % (vuelve al ~90 %).
    Umbral del seed: 20 por abajo, así que no salta alerta en funcionamiento normal."""

    RELLENAR_EN = 35.0
    LLENO = 90.0

    def __init__(self, codigo: str, semilla: int | None = None) -> None:
        super().__init__(codigo, semilla)
        self.nivel = self.azar.uniform(55, 85)

    def avanzar(self, instante: datetime, paso: timedelta) -> float:
        horas = paso.total_seconds() / 3600
        self.nivel -= 0.3 * horas
        if self.nivel < self.RELLENAR_EN:
            self.nivel = self.LLENO
        return round(_limitar(self.nivel + self.ruido(0.1), 0, 100), 1)


# Tipo de sensor (los de ``UNIDAD_POR_TIPO``) -> clase de su modelo.
MODELO_POR_TIPO: dict[str, type[Modelo]] = {
    "temperatura": Temperatura,
    "humedad_suelo": HumedadSuelo,
    "luminosidad": Luminosidad,
    "humedad_ambiente": HumedadAmbiente,
    "nivel_deposito": NivelDeposito,
}


def crear_modelo(codigo: str, tipo: str, semilla: int | None = None) -> Modelo:
    """El modelo adecuado para un sensor. Un tipo desconocido es un error de programación."""
    return MODELO_POR_TIPO[tipo](codigo, semilla)
