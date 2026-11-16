"""Regenera los PNG de docs/wireframes/ a partir de wireframes.html.

Uso (desde la raíz del repo):
    pip install playwright && playwright install chromium
    python docs/wireframes/fuente/capturar.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

AQUI = Path(__file__).resolve().parent
PANTALLAS = ["01-inicio", "02-login", "03-dashboard", "04-parcela-sensor", "05-alertas", "06-ajustes"]

with sync_playwright() as p:
    navegador = p.chromium.launch()
    pagina = navegador.new_page(viewport={"width": 2100, "height": 1000})
    pagina.goto((AQUI / "wireframes.html").as_uri())
    for i, nombre in enumerate(PANTALLAS, start=1):
        # cada pantalla es un <section class="sheet" id="sN">
        pagina.locator(f"#s{i}").screenshot(path=AQUI.parent / f"{nombre}.png")
    navegador.close()
