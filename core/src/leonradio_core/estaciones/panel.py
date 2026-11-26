"""Panel de resumen de una estación (marcador de posición mientras no tiene paneles propios)."""

from __future__ import annotations

from .. import sdk
from ..uischema import UI


def make_panel(key: str) -> type[sdk.Editor]:
    from . import STATIONS

    info = STATIONS[key]

    class StationPanel(sdk.Editor):
        id, label, icon = key, info["nombre"], "▣"
        station = key

        def draw(self, ui: UI, ctx: sdk.Context) -> None:
            ui.label(info["nombre"].upper(), "accent")
            ui.label(info["estado"].capitalize(), "title")
            ui.label("Alcance", "muted")
            for line in info["alcance"]:
                ui.label("· " + line)
            ui.label("Tareas en docs/ROADMAP.md: " + ", ".join(info["tareas"]), "muted")

    StationPanel.__name__ = f"Panel_{key}"
    return StationPanel
