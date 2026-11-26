"""Estación programacion: aquí van SUS paneles y comandos (ver docs/estaciones.md)."""

from __future__ import annotations

from ... import sdk
from ..panel import make_panel


def register(host: sdk.Host) -> None:
    sdk.register_editor(make_panel("programacion"))
    # Nuevos paneles de esta estación: sdk.register_editor(MiPanel); comandos: host.register_command(...)
