"""Estación Al Aire. Sus paneles actuales viven aún en `builtin/` (Aire, Controles, Emisión, Auxiliares, Varios…).

Los paneles NUEVOS de Al Aire (escaleta, guiones, invitados…) se crean aquí. Mover los existentes desde `builtin/`
es la tarea S9 del ROADMAP; mientras tanto no se duplican.
"""

from __future__ import annotations

from ... import sdk


def register(host: sdk.Host) -> None:
    return None
