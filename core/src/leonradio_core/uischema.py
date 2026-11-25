"""UI declarativa: el editor describe su panel en Python y la UI lo dibuja con la marca.

Cada nodo es un dict serializable a JSON: {"t": "<tipo>", ...}. Tipos:
label, kv, button, progress, separator, table, row, column.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

TONES = {"normal", "muted", "accent", "big", "mono", "ok", "warn"}


class UI:
    def __init__(self) -> None:
        self.root: dict[str, Any] = {"t": "column", "children": []}
        self._stack = [self.root]

    def _add(self, node: dict[str, Any]) -> dict[str, Any]:
        self._stack[-1]["children"].append(node)
        return node

    def label(self, text: object, tone: str = "normal") -> None:
        if tone not in TONES:
            raise ValueError(f"tono desconocido: {tone}")
        self._add({"t": "label", "text": str(text), "tone": tone})

    def kv(self, key: str, value: object) -> None:
        self._add({"t": "kv", "key": key, "value": str(value)})

    def button(self, label: str, command: str, args: dict | None = None) -> None:
        self._add({"t": "button", "label": label, "command": command, "args": args or {}})

    def progress(self, value: float, text: str | None = None) -> None:
        self._add({"t": "progress", "value": max(0.0, min(1.0, float(value))), "text": text})

    def custom(self, component: str, **props: Any) -> None:
        """Componente JS incluido en la UI (vu-meter, analog-clock, fm-dial, cartwall…).
        Las props deben ser JSON; el componente se dibuja en el navegador."""
        self._add({"t": "custom", "component": component, "props": props})

    def separator(self) -> None:
        self._add({"t": "separator"})

    def table(self, columns: list[str], rows: list[list[object]], narrow_hide: list[int] | None = None) -> None:
        """`narrow_hide`: índices de columnas que se ocultan cuando el área es angosta (p. ej. en el teléfono)."""
        self._add({"t": "table", "columns": columns, "nh": narrow_hide or [],
                   "rows": [[str(c) if c is not None else "" for c in r] for r in rows]})

    @contextmanager
    def row(self) -> Iterator[None]:
        yield from self._container("row")

    @contextmanager
    def column(self) -> Iterator[None]:
        yield from self._container("column")

    def _container(self, kind: str) -> Iterator[None]:
        node = self._add({"t": kind, "children": []})
        self._stack.append(node)
        try:
            yield
        finally:
            self._stack.pop()

    def build(self) -> dict[str, Any]:
        return self.root
