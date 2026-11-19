"""Tema visual de Demeter: paleta, tipografía y medidas (C2, issue #29).

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
}

# ---------------------------------------------------------------- tipografía
FUENTES: dict[str, str] = {
    "sans": "'Mona Sans', system-ui, -apple-system, 'Segoe UI', sans-serif",
    "serif": "'Instrument Serif', Georgia, serif",  # solo cursiva, para acentos
    "mono": "'Geist Mono', ui-monospace, 'SFMono-Regular', monospace",  # cifras y etiquetas
}
GOOGLE_FONTS = (
    "https://fonts.googleapis.com/css2?family=Mona+Sans:wdth,wght@75..125,400..800"
    "&family=Instrument+Serif:ital@1&family=Geist+Mono:wght@400;500&display=swap"
)

# ---------------------------------------------------------------- medidas
MEDIDAS: dict[str, str] = {
    "radio": "14px",
    "radio_grande": "22px",
    "barra_alto": "64px",  # barra superior en escritorio
    "pestanas_alto": "64px",  # pestañas inferiores en móvil
    "ancho_max": "1200px",
}
# Por debajo de este ancho la barra superior se convierte en pestañas abajo.
CORTE_MOVIL_PX = 760


def variables_css() -> str:
    """Las variables ``--dm-*`` (``COLORES['papel']`` → ``--dm-papel``)."""
    pares = [*COLORES.items(), *(("fuente-" + k, v) for k, v in FUENTES.items()), *MEDIDAS.items()]
    return "\n".join(f"  --dm-{k.replace('_', '-')}: {v};" for k, v in pares)


def css_global() -> str:
    """CSS común a todas las páginas: variables, base y el responsive del layout.

    Se inyecta una vez en el ``<head>`` desde ``demeter/demeter.py``.
    """
    m = CORTE_MOVIL_PX
    return f""":root {{
{variables_css()}
}}
html, body {{ margin: 0; background: var(--dm-papel); color: var(--dm-tinta);
  font-family: var(--dm-fuente-sans); -webkit-font-smoothing: antialiased; }}
a {{ color: inherit; }}
.dm-shell {{ min-height: 100dvh; display: flex; flex-direction: column; }}

/* Barra superior (escritorio) */
.dm-bar {{ position: sticky; top: 0; z-index: 20; height: var(--dm-barra-alto);
  display: flex; align-items: center; gap: 28px; padding: 0 24px;
  background: color-mix(in srgb, var(--dm-papel) 86%, transparent);
  backdrop-filter: blur(12px); border-bottom: 1px solid var(--dm-linea); }}
.dm-marca {{ display: flex; align-items: center; gap: 10px; text-decoration: none; }}
.dm-marca img {{ width: 30px; height: 30px; }}
.dm-marca span {{ font-weight: 800; font-stretch: 75%; font-size: 24px; letter-spacing: .01em; }}
.dm-nav {{ display: flex; gap: 4px; }}
.dm-nav a {{ position: relative; padding: 8px 12px; border-radius: 10px; text-decoration: none;
  color: var(--dm-tinta-suave); font-weight: 500; }}
.dm-nav a:hover {{ color: var(--dm-tinta); background: var(--dm-papel-2); }}
.dm-nav a[aria-current="page"] {{ color: var(--dm-tinta); background: var(--dm-papel-2); }}
.dm-badge {{ display: inline-grid; place-items: center; min-width: 18px; height: 18px; padding: 0 5px;
  margin-left: 6px; border-radius: 99px; background: var(--dm-acento); color: #fff;
  font: 500 11px/1 var(--dm-fuente-mono); }}
.dm-bar__fin {{ margin-left: auto; display: flex; align-items: center; gap: 12px; }}

/* Contenido */
.dm-main {{ flex: 1; width: 100%; max-width: var(--dm-ancho-max); margin: 0 auto;
  padding: 32px 24px 48px; box-sizing: border-box; min-width: 0; }}
.dm-titulo {{ margin: 0 0 6px; font-size: clamp(28px, 4vw, 40px); font-weight: 600; letter-spacing: -.03em; }}
.dm-sub {{ margin: 0 0 28px; color: var(--dm-tinta-suave); }}
.dm-rejilla {{ display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); }}
.dm-tarjeta {{ background: var(--dm-papel-2); border: 1px solid var(--dm-linea);
  border-radius: var(--dm-radio-grande); padding: 20px; min-width: 0; }}
.dm-hueco {{ border-style: dashed; color: var(--dm-tinta-suave); }}
.dm-etiqueta {{ font: 500 12px/1.4 var(--dm-fuente-mono); letter-spacing: .08em; text-transform: uppercase;
  color: var(--dm-tinta-suave); }}
.dm-boton {{ display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 44px;
  padding: 0 20px; border: 0; border-radius: 12px; background: var(--dm-acento); color: #fff;
  font: 600 15px/1 var(--dm-fuente-sans); text-decoration: none; cursor: pointer; }}
.dm-boton:hover {{ filter: brightness(1.08); }}
.dm-boton--sec {{ background: transparent; color: var(--dm-tinta); border: 1px solid var(--dm-linea); }}
:focus-visible {{ outline: 2px solid var(--dm-acento); outline-offset: 2px; }}

/* Pestañas inferiores (móvil) */
.dm-pestanas {{ display: none; }}
@media (max-width: {m}px) {{
  .dm-nav, .dm-bar__fin .dm-usuario {{ display: none; }}
  .dm-bar {{ padding: 0 16px; }}
  .dm-main {{ padding: 20px 16px calc(var(--dm-pestanas-alto) + 28px); }}
  .dm-pestanas {{ display: grid; grid-template-columns: repeat(4, 1fr); position: fixed; inset: auto 0 0;
    z-index: 20; height: calc(var(--dm-pestanas-alto) + env(safe-area-inset-bottom));
    padding-bottom: env(safe-area-inset-bottom); background: var(--dm-tinta); }}
  .dm-pestanas a {{ display: grid; place-items: center; align-content: center; gap: 4px; text-decoration: none;
    color: rgba(255, 255, 255, .62); font-size: 11px; -webkit-tap-highlight-color: transparent; }}
  .dm-pestanas a[aria-current="page"] {{ color: #fff; }}
  .dm-pestanas svg {{ width: 22px; height: 22px; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
"""
