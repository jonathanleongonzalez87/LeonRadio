"""Backend de DEMOSTRACIÓN: ejecuta el motor completo dentro del navegador (Pyodide), sin servidor ni audio.

Lo usa el HTML autónomo que genera `tools/build_demo.py`. Hace lo mismo que `server.py`, sin FastAPI:
la UI llama a `info()`, `editors()`, `draw()`, `run()` y `tick()`, y los eventos se devuelven por lotes.
Todo se intercambia como JSON (cadenas), que es lo más simple de cruzar entre Python y JavaScript.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import addons, builtin, sdk


class DemoBackend:
    def __init__(self, root: str = ".") -> None:
        self.host = sdk.Host()
        self._events: list[dict] = []
        with self.host.db_lock:
            for i, a in enumerate(sdk.load_json("demo_library.json")["assets"]):
                self.host.db.execute(
                    "INSERT INTO assets (path, kind, title, artist, decade, duration_ms) VALUES (?,?,?,?,?,?)",
                    (f"demo://{i}", a["kind"], a["title"], a.get("artist"), a.get("decade"), a["duration_ms"]))
            self.host.db.commit()
        self.playout = builtin.register(self.host)
        self.loaded = addons.discover(self.host, Path(root) / "addons")
        self.host.events.subscribe(lambda name, data: self._events.append({"event": name, "data": data}))

    @staticmethod
    def _dump(obj: object) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)

    def info(self) -> str:
        return self._dump({
            "station": self.host.station, "config": self.host.config, "api_version": sdk.API_VERSION,
            "addons": [{"id": m.id, "name": m.name, "version": m.version, "permissions": sorted(m.permissions)}
                       for m in self.loaded]})

    def editors(self) -> str:
        return self._dump([{"id": e.id, "label": e.label, "icon": e.icon, "owner": owner}
                           for e, owner, _ in self.host.editors.values()])

    def draw(self, editor_id: str) -> str:
        if editor_id not in self.host.editors:
            return self._dump({"error": f"editor desconocido: {editor_id}"})
        return self._dump(self.host.draw_editor(editor_id))

    def run(self, name: str, args_json: str = "{}") -> str:
        try:
            result = self.host.run_command(name, json.loads(args_json or "{}"))
        except KeyError:
            return self._dump({"ok": False, "error": f"comando desconocido: {name}"})
        except (sdk.PermissionDenied, ValueError) as exc:
            return self._dump({"ok": False, "error": str(exc)})
        return self._dump({"ok": True, "result": result if isinstance(result, (str, int, float, bool, dict, list, type(None))) else None})

    def tick(self, seconds: float) -> str:
        """Avanza el reproductor simulado y devuelve (JSON) los eventos ocurridos desde la última llamada."""
        self.playout.tick(float(seconds))
        out, self._events = self._events, []
        return self._dump(out)


def create(root: str = ".") -> DemoBackend:
    return DemoBackend(root)
