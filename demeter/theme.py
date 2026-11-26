"""Tema visual de Demeter: paleta, tipografía y medidas (C2, issue #29).

Son los valores del prototipo «Demeter web completa con Demetreo griego».

Todo el aspecto de la app sale de aquí. Si el equipo cambia la paleta, se cambia
solo en este archivo (y en ``docs/diseno.md``): las páginas usan las variables CSS
``--dm-*`` que genera :func:`css_global`, nunca colores escritos a mano.
"""

from __future__ import annotations

# ---------------------------------------------------------------- paleta
# Valores del prototipo de la portada. El contraste de cada texto sobre ``papel``
# está comprobado en docs/diseno.md (WCAG AA como mínimo).
COLORES: dict[str, str] = {
    "tinta": "#12181a",  # texto principal y barra en móvil
    "tinta_suave": "#56626a",  # texto secundario (5,4:1 sobre papel)
    "papel": "#eceeed",  # fondo de la app
    "papel_2": "#e3e6e5",  # tarjetas y zonas hundidas
    "linea": "rgba(18, 24, 26, .13)",  # bordes finos
    "acento": "#b33a12",  # terracota: botones, enlaces y alertas
    "acento_suave": "rgba(179, 58, 18, .10)",
    "ok": "#2f8a63",  # solo puntos de estado; NO para texto (contraste bajo)
    "ok_texto": "#1f6b4c",  # verde para texto («en rango»)
    "campo": "#3e5a22",  # verde oliva de Demetreo, para fondos de marca
    "sin_senal": "#8a9499",  # gris de tarjeta offline: punto, borde y mini histórico
    "sin_senal_fondo": "rgba(18, 24, 26, .05)",  # fondo de la tarjeta offline
}

# ---------------------------------------------------------------- semáforo
# Cómo se pinta cada ``SensorStatus`` (demeter/state/types.py) en la tarjeta del
# dashboard. ``clase`` es el modificador CSS de assets/proto/app.css
# (``srow--off``, ``ro is-off``…); ``color`` es una clave de COLORES.
# Los textos van siempre en ``tinta`` o ``tinta_suave``: el color solo marca el punto,
# así el gris de «offline» no tiene problemas de contraste.
ESTADOS_SENSOR: dict[str, dict[str, str]] = {
    "ok": {"etiqueta": "En rango", "clase": "", "color": "ok"},
    "LOW": {"etiqueta": "Bajo", "clase": "warn", "color": "acento"},
    "HIGH": {"etiqueta": "Alto", "clase": "warn", "color": "acento"},
    "offline": {"etiqueta": "Sin señal", "clase": "off", "color": "sin_senal"},
    "sin_datos": {"etiqueta": "Esperando datos", "clase": "wait", "color": "linea"},
}


def estado_sensor(status: str) -> dict[str, str]:
    """Etiqueta, clase y color de un estado; uno desconocido se trata como «sin datos»."""
    return ESTADOS_SENSOR.get(status, ESTADOS_SENSOR["sin_datos"])

# ---------------------------------------------------------------- tipografía
FUENTES: dict[str, str] = {
    "sans": "'Mona Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "serif": "'Instrument Serif', Georgia, serif",  # solo cursiva, para acentos
    "mono": "'Geist Mono', ui-monospace, 'SFMono-Regular', monospace",  # cifras y etiquetas
}
GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Instrument+Serif:ital@1"
    "&family=Mona+Sans:wdth,wght@75..125,200..900&family=Geist+Mono:wght@400..500&display=swap"
)
# Hojas del prototipo (assets/proto/), en el orden en que se cargan.
HOJAS_PORTADA = ("/proto/proto.css", "/proto/cabina/cabina.css", "/proto/mascota.css")
HOJAS_APP = ("/proto/proto.css", "/proto/app.css", "/proto/mascota.css")

# ---------------------------------------------------------------- medidas
MEDIDAS: dict[str, str] = {
    "radio": "14px",
    "radio_grande": "22px",
    "barra_alto": "64px",  # barra superior en escritorio
    "pestanas_alto": "64px",  # pestañas inferiores en móvil
    "ancho_max": "1200px",
}
# Por debajo de este ancho la barra superior se convierte en pestañas abajo
# (lo aplica assets/proto/app.css).
CORTE_MOVIL_PX = 760


def variables_css() -> str:
    """Las variables ``--dm-*`` (``COLORES['papel']`` → ``--dm-papel``)."""
    pares = [*COLORES.items(), *(("fuente-" + k, v) for k, v in FUENTES.items()), *MEDIDAS.items()]
    return "\n".join(f"  --dm-{k.replace('_', '-')}: {v};" for k, v in pares)


def css_global() -> str:
    """Variables ``--dm-*`` para el código Reflex nuevo.

    El aspecto actual de las páginas lo dan las hojas del prototipo en
    ``assets/proto/`` (mismos colores que aquí). Cuando cada rama sustituya su
    plantilla por componentes Reflex, usará estas variables en lugar de las del
    prototipo; así hay una sola fuente de verdad para la paleta.
    """
    return f":root {{\n{variables_css()}\n}}\n"
