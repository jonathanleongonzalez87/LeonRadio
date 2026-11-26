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
    page.mouse.move(0, 0)  # sin cursor sobre las áreas (si no, aparece su encabezado compacto)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(OUT / f"{name}.png"))
    print("guardado", OUT / f"{name}.png")


with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    page.goto(URL)
    page.wait_for_selector("#splash.ready")                 # pantalla de carga: se queda hasta que se hace clic
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / "splash.png"))
    print("guardado", OUT / "splash.png")
    page.click("#splash")
    page.wait_for_selector(".area .body .u-col, .area .body .cmp")
    page.wait_for_timeout(2500)

    # algo de actividad para que Historial y Cartuchera tengan contenido
    for _ in range(2):
        page.locator('button[title="Siguiente"]').first.dispatch_event('click')
        page.wait_for_timeout(700)
    for key in ("Numpad1", "Numpad3", "Numpad6"):           # botonera: teclado numérico
        page.keyboard.press(key)
        page.wait_for_timeout(500)
    # listas auxiliares desde la barra de herramientas + Explorador de la Botonera
    page.click('.aux-btn[data-n="1"]')
    page.click('.aux-btn[data-n="2"]')
    page.get_by_role("tab", name="Explorador").click()
    page.get_by_role("button", name="Aux 1", exact=True).click()
    for i in range(3):
        page.get_by_role("button", name="＋").nth(i).click()
        page.wait_for_timeout(300)
    page.locator('button[title="Reproducir"]').last.dispatch_event('click')
    shot(page, "botonera-explorador")
    page.get_by_role("tab", name="Botonera", exact=True).click()
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

    # teléfono: las áreas se apilan; captura de la página completa
    phone = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                is_mobile=True, has_touch=True)
    mp = phone.new_page()
    mp.goto(URL)
    mp.wait_for_selector("#splash.ready")
    mp.click("#splash")
    mp.wait_for_selector(".area .body")
    mp.wait_for_timeout(3000)
    mp.screenshot(path=str(OUT / "telefono-aire.png"))
    print("guardado", OUT / "telefono-aire.png")
    mp.get_by_role("tab", name="Producción").click()
    mp.wait_for_timeout(1500)
    mp.screenshot(path=str(OUT / "telefono-produccion.png"))
    print("guardado", OUT / "telefono-produccion.png")
    browser.close()
