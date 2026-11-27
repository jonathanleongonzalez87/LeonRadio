"""Estación produccion: aquí van SUS paneles y comandos (ver docs/estaciones.md)."""

from __future__ import annotations

from ... import sdk
from ..panel import make_panel


def register(host: sdk.Host) -> None:
    from . import comercial, entidades, paneles   # import tardío: db importa este paquete antes que entities (como Programación)

    sdk.register_editor(make_panel("produccion"))
    for entity in entidades.ALL:
        host.entities.declare(entity)
    comercial.register(host)
    sdk.register_editor(paneles.ComercialPanel)
    # Nuevos paneles de esta estación: sdk.register_editor(MiPanel); comandos: host.register_command(...)
