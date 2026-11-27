"""Estación programacion: aquí van SUS paneles y comandos (ver docs/estaciones.md)."""

from __future__ import annotations

from ... import sdk
from ..panel import make_panel


def register(host: sdk.Host) -> None:
    from ...entities import register_crud     # import tardío: db importa este paquete (ver db.py) antes que entities
    from . import catalogo, entidades

    sdk.register_editor(make_panel("programacion"))
    for entity in entidades.ALL:
        host.entities.declare(entity)
    register_crud(host, "programacion", ["artista", "album", "genero"])   # Pieza no: la escribe el escáner
    catalogo.register(host)
    try:
        catalogo.sync(host)
    except Exception:  # noqa: BLE001 - sin vínculos el resto de la estación funciona; se reintenta con catalogo.sincronizar
        sdk.log.exception("no se pudo sincronizar el catálogo musical")
    # Nuevos paneles de esta estación: sdk.register_editor(MiPanel); comandos: host.register_command(...)
