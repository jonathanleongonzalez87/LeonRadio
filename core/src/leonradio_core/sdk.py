"""API pública para editores y addons (v0).

Los editores incluidos (`builtin/`) usan EXACTAMENTE esta misma API que un addon.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from . import db as _db
from . import playlog as _playlog
from .events import EventBus
from .uischema import UI

API_VERSION = "0.1"
log = logging.getLogger("leonradio.sdk")

_DATA = Path(__file__).parent / "data"


def load_json(name: str):
    """Datos de ejemplo/configuración empaquetados en `leonradio_core/data/`."""
    return json.loads((_DATA / name).read_text(encoding="utf-8"))


PERMISSIONS = {"library.read", "playlog.read", "playlog.write", "state.write", "network"}


class PermissionDenied(PermissionError):
    pass


class Editor:
    """Base de un editor. Subclase: define `id`, `label` y `draw(ui, ctx)`."""

    id: str = ""
    label: str = ""
    icon: str = "▣"

    def draw(self, ui: UI, ctx: "Context") -> None:  # pragma: no cover - interfaz
        raise NotImplementedError


class Context:
    """Lo que ve un editor/comando: estado de solo lectura + servicios con permisos."""

    def __init__(self, host: "Host", owner: str, permissions: frozenset[str]) -> None:
        self._host, self.owner, self.permissions = host, owner, permissions

    def _need(self, perm: str) -> None:
        if perm not in self.permissions:
            raise PermissionDenied(f"{self.owner} no tiene el permiso '{perm}'")

    @property
    def config(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._host.config))

    @property
    def state(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._host.state))

    def set_state(self, key: str, value: Any) -> None:
        self._need("state.write")
        self._host.set_state(f"{self.owner}.{key}" if self.owner != "builtin" else key, value)

    def recent_plays(self, limit: int = 20) -> list[dict]:
        self._need("playlog.read")
        with self._host.db_lock:
            rows = self._host.db.execute(
                "SELECT started_at, kind, title, artist, source, status FROM playlog "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def library(self, kind: str | None = None, limit: int = 200, decade: str | None = None) -> list[dict]:
        self._need("library.read")
        sql, params = "SELECT id, kind, title, artist, decade, duration_ms FROM assets WHERE status='active'", []
        if kind:
            sql += " AND kind = ?"; params.append(kind)
        if decade:
            sql += " AND decade = ?"; params.append(decade)
        with self._host.db_lock:
            rows = self._host.db.execute(sql + " ORDER BY title LIMIT ?", (*params, limit)).fetchall()
        return [dict(r) for r in rows]

    def library_groups(self) -> list[dict]:
        """Grupos de la biblioteca (tipo + década) con su cantidad de piezas."""
        self._need("library.read")
        with self._host.db_lock:
            rows = self._host.db.execute(
                "SELECT kind, decade, COUNT(*) AS n FROM assets WHERE status='active' "
                "GROUP BY kind, decade ORDER BY kind, decade").fetchall()
        return [dict(r) for r in rows]

    def emit(self, name: str, data: dict | None = None) -> None:
        self._host.events.emit(f"{self.owner}.{name}" if self.owner != "builtin" else name, data)


class Host:
    """Estado compartido del programa: registros, bus de eventos, base de datos."""

    def __init__(self, db_path: str = ":memory:", config: dict | None = None) -> None:
        self.config: dict[str, Any] = config or load_json("station.json")
        self.station: str = self.config["short"]
        self.db = _db.connect(db_path, shared=True)
        self.db_lock = threading.RLock()
        self.events = EventBus()
        self.state: dict[str, Any] = {}
        self.editors: dict[str, tuple[Editor, str, frozenset[str]]] = {}
        self.commands: dict[str, tuple[Callable[..., Any], str, frozenset[str]]] = {}

    # -- estado ---------------------------------------------------------
    def set_state(self, key: str, value: Any) -> None:
        self.state[key] = value
        self.events.emit("state_changed", {"key": key})

    # -- registro ----------------------------------------------------------
    def register_editor(self, editor: Editor, owner: str = "builtin",
                        permissions: frozenset[str] = frozenset(PERMISSIONS)) -> None:
        if not editor.id or not editor.label:
            raise ValueError("un editor necesita `id` y `label`")
        if editor.id in self.editors:
            raise ValueError(f"editor duplicado: {editor.id}")
        self.editors[editor.id] = (editor, owner, permissions)

    def unregister_editor(self, editor_id: str) -> None:
        self.editors.pop(editor_id, None)

    def register_command(self, name: str, fn: Callable[..., Any], owner: str = "builtin",
                         permissions: frozenset[str] = frozenset(PERMISSIONS)) -> None:
        if name in self.commands:
            raise ValueError(f"comando duplicado: {name}")
        self.commands[name] = (fn, owner, permissions)

    def unregister_owner(self, owner: str) -> None:
        for k in [k for k, v in self.editors.items() if v[1] == owner]:
            del self.editors[k]
        for k in [k for k, v in self.commands.items() if v[1] == owner]:
            del self.commands[k]

    # -- uso -------------------------------------------------------------
    def draw_editor(self, editor_id: str) -> dict:
        editor, owner, perms = self.editors[editor_id]
        ui = UI()
        try:
            editor.draw(ui, Context(self, owner, perms))
        except Exception as exc:  # un editor roto muestra su error; no tumba la app
            log.exception("editor %s falló", editor_id)
            ui = UI()
            ui.label(f"Error en el editor «{editor.label}»", "warn")
            ui.label(f"{type(exc).__name__}: {exc}", "muted")
        return ui.build()

    def run_command(self, name: str, args: dict | None = None) -> Any:
        fn, owner, perms = self.commands[name]
        return fn(Context(self, owner, perms), **(args or {}))

    def record_play(self, **kw: Any) -> int:
        with self.db_lock:
            rid = _playlog.record_play(self.db, station=self.station, **kw)
        self.events.emit("playlog.added", {"id": rid})
        return rid


# --- API de módulo: la que usan los addons (`import leonradio as lr`) ------
_current: Host | None = None
_current_owner: tuple[str, frozenset[str]] = ("builtin", frozenset(PERMISSIONS))


def bind(host: Host, owner: str = "builtin", permissions: frozenset[str] | None = None) -> None:
    """Uso interno: fija el host y el dueño mientras se carga un addon."""
    global _current, _current_owner
    _current = host
    _current_owner = (owner, frozenset(PERMISSIONS) if permissions is None else permissions)


def _host() -> Host:
    if _current is None:
        raise RuntimeError("LeonRadio no está iniciado")
    return _current


def register_editor(editor: type[Editor] | Editor) -> None:
    inst = editor() if isinstance(editor, type) else editor
    _host().register_editor(inst, *_current_owner)


def unregister_editor(editor: type[Editor] | Editor) -> None:
    _host().unregister_editor(editor.id)


def command(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorador: registra un comando. Se activa al llamar `register_command` o al cargar el módulo."""
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        fn._lr_command = name  # type: ignore[attr-defined]
        _host().register_command(name, fn, *_current_owner)
        return fn
    return deco


def register_command(fn: Callable[..., Any]) -> None:
    name = getattr(fn, "_lr_command", None)
    if name and name not in _host().commands:
        _host().register_command(name, fn, *_current_owner)
