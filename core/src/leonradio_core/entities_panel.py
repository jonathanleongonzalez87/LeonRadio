"""Panel común «Entidades»: qué datos compartidos existen y quién los escribe (solo lectura)."""

from __future__ import annotations

from . import sdk
from .estaciones import STATIONS
from .uischema import UI


class EntidadesEditor(sdk.Editor):
    id, label, icon = "entidades", "Entidades", "▤"
    station = ""

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        rows = [[c["etiqueta"], c["que_es"], STATIONS[c["dueno"]]["nombre"], c["activos"], c["archivados"],
                 c["estado"] + (f" · {c['nota']}" if c["nota"] else "")] for c in ctx.entities.catalog()]
        ui.table(["Entidad", "Qué es", "Dueño", "Activos", "Archivados", "Estado"], rows)
        ui.label("Solo lectura. Cada estación edita sus entidades en sus propias pantallas.", "muted")
