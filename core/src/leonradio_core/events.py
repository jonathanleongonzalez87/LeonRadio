"""Bus de eventos: algo ocurrió (`track_started`, `playlog.added`…)."""

from __future__ import annotations

import logging
from typing import Any, Callable

log = logging.getLogger("leonradio.events")
Listener = Callable[[str, dict[str, Any]], None]


class EventBus:
    def __init__(self) -> None:
        self._listeners: list[Listener] = []

    def subscribe(self, fn: Listener) -> Callable[[], None]:
        self._listeners.append(fn)
        return lambda: self._listeners.remove(fn) if fn in self._listeners else None

    def emit(self, name: str, data: dict[str, Any] | None = None) -> None:
        for fn in list(self._listeners):
            try:
                fn(name, data or {})
            except Exception:  # un oyente defectuoso nunca debe frenar a los demás
                log.exception("oyente falló en evento %s", name)
