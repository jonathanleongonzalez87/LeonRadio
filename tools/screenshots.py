"""Genera los pantallazos de docs/img/ con la UI en marcha.

Requisitos (fuera de las dependencias del proyecto):
    pip install playwright          # usa el Edge instalado; no descarga navegadores
Uso:
    leonradio serve --library "<carpeta de la emisora>"      # en otra terminal
    python tools/screenshots.py [http://127.0.0.1:8765] [docs/img]
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "docs" / "img")
OUT.mkdir(parents=True, exist_ok=True)


def shot(page, name: str) -> None:
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("guardado", OUT / f"{name}.png")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(URL)
    page.wait_for_selector(".area .body .u-col, .area .body .cmp")
    page.wait_for_timeout(2500)

    # algo de actividad para que Historial y Cartuchera tengan contenido
    for _ in range(2):
        page.get_by_role("button", name="Siguiente").first.click()
        page.wait_for_timeout(700)
    for key in ("F1", "F3", "F6"):
        page.keyboard.press(key)
        page.wait_for_timeout(500)
    shot(page, "aire-oscuro")

    page.get_by_role("tab", name="Producción").click()
    page.get_by_role("button", name="Pulsar").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Pulsar").click()
    shot(page, "produccion-addon")

    page.get_by_role("tab", name="Programación").click()
    shot(page, "programacion")

    page.get_by_role("tab", name="Aire").click()
    page.click("#theme")
    shot(page, "aire-claro")
    browser.close()
