"""UI declarativa: el editor describe su panel en Python y la UI lo dibuja con la marca.

Cada nodo es un dict serializable a JSON: {"t": "<tipo>", ...}. Tipos:
label, kv, button, progress, separator, table, row, column.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

TONES = {"normal", "muted", "accent", "big", "mono", "ok", "warn", "title"}


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

    def button(self, label: str, command: str, args: dict | None = None, size: str = "md",
               selected: bool = False) -> None:
        """`size`: "md" | "sm". `selected`: botón encendido (p. ej. la opción elegida de un grupo)."""
        self._add({"t": "button", "label": label, "command": command, "args": args or {},
                   "size": size, "selected": bool(selected)})

    def progress(self, value: float, text: str | None = None) -> None:
        self._add({"t": "progress", "value": max(0.0, min(1.0, float(value))), "text": text})

    def slider(self, value_ms: float, total_ms: float, command: str, args: dict | None = None, suffix: str = "") -> None:
        """Barra de reproducción con control deslizante: al soltarla se ejecuta `command` con args + {"ms": posición}."""
        self._add({"t": "slider", "value": max(0.0, float(value_ms)), "max": max(1.0, float(total_ms)),
                   "command": command, "args": args or {}, "suffix": suffix})

    def custom(self, component: str, **props: Any) -> None:
        """Componente JS incluido en la UI (vu-meter, analog-clock, fm-dial, cartwall…).
        Las props deben ser JSON; el componente se dibuja en el navegador."""
        self._add({"t": "custom", "component": component, "props": props})

    def separator(self) -> None:
        self._add({"t": "separator"})

    def table(self, columns: list[str], rows: list[list[object]], narrow_hide: list[int] | None = None,
              file_list: dict | None = None) -> None:
        """`narrow_hide`: índices de columnas que se ocultan cuando el área es angosta (p. ej. en el teléfono).
        `file_list`: {"target", "uids", "selected"} hace las filas elegibles (clic), arrastrables y borrables (Supr)."""
        self._add({"t": "table", "columns": columns, "nh": narrow_hide or [], "list": file_list,
                   "rows": [[c if isinstance(c, dict) else (str(c) if c is not None else "") for c in r] for r in rows]})

    @staticmethod
    def actions(*buttons: tuple[str, str, dict]) -> dict:
        """Celda de tabla con botones pequeños: cada uno es (texto, comando, args)."""
        return {"actions": [{"label": l, "command": c, "args": a} for l, c, a in buttons]}

    @contextmanager
    def row(self, cls: str | None = None) -> Iterator[None]:
        yield from self._container("row", cls)

    @contextmanager
    def column(self, cls: str | None = None) -> Iterator[None]:
        yield from self._container("column", cls)

    @contextmanager
    def tabs(self, id: str) -> Iterator["_Tabs"]:
        """Pestañas: `with ui.tabs("id") as t: with t.tab("Nombre"): ...`. El `id` recuerda la pestaña activa."""
        node = self._add({"t": "tabs", "id": id, "tabs": []})
        yield _Tabs(self, node)

    def _container(self, kind: str, cls: str | None = None) -> Iterator[None]:
        node = self._add({"t": kind, "children": []})
        if cls:
            node["cls"] = cls
        self._stack.append(node)
        try:
            yield
        finally:
            self._stack.pop()

    def build(self) -> dict[str, Any]:
        return self.root


class _Tabs:
    def __init__(self, ui: UI, node: dict[str, Any]) -> None:
        self._ui, self._node = ui, node

    @contextmanager
    def tab(self, label: str) -> Iterator[None]:
        t: dict[str, Any] = {"label": label, "children": []}
        self._node["tabs"].append(t)
        self._ui._stack.append(t)
        try:
            yield
        finally:
            self._ui._stack.pop()
