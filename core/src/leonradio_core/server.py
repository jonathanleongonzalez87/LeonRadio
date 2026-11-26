"""Servidor: API REST + WebSocket de eventos + archivos de la UI.

    leonradio serve [--library CARPETA] [--port 8765]
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import addons, builtin, library, meta, sdk, settings
from .engine.output import make_output

log = logging.getLogger("leonradio.server")
REPO = Path(__file__).resolve().parents[3]  # <repo>/core/src/leonradio_core/server.py


class NoCacheStatic(StaticFiles):
    """Archivos de la UI siempre revalidados: al desarrollar, el navegador no se queda con versiones viejas."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


class CommandBody(BaseModel):
    args: dict = {}


def _friendly(exc: Exception) -> str:
    """Mensaje corto para la interfaz (los errores de PortAudio traen códigos largos)."""
    text = str(exc)
    if "PortAudio" in type(exc).__name__ or "host error" in text:
        return "Ese dispositivo no se pudo abrir (puede estar en uso, desconectado o no admitir el formato). Prueba otro de la lista o de otra interfaz."
    return text or type(exc).__name__


def create_app(
    *, library_dir: str | None = None, db_path: str = ":memory:",
    addon_dirs: list[Path] | None = None, ui_dir: Path | None = None, tick: bool = True,
    audio: str = "null", device: str | int | None = None, autoplay: bool | None = None,
) -> FastAPI:
    host = sdk.Host(db_path=db_path)
    host.library_dir = library_dir
    if library_dir:
        library.scan(host.db, library_dir)
    saved_routes = settings.load().get("audio", {}).get("routes", {})
    playout = builtin.register(host, output=make_output(audio, device, saved_routes), autoplay=autoplay)
    roots = addon_dirs if addon_dirs is not None else [REPO / "addons"]
    env = os.environ.get("LEONRADIO_ADDONS")
    if env and addon_dirs is None:
        roots += [Path(p) for p in env.split(os.pathsep) if p]
    loaded = addons.discover(host, *roots)

    clients: set[WebSocket] = set()
    queue: asyncio.Queue = asyncio.Queue()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        host.events.subscribe(lambda n, d: loop.call_soon_threadsafe(queue.put_nowait, {"event": n, "data": d}))

        async def broadcaster() -> None:
            while True:
                msg = await queue.get()
                for ws in list(clients):
                    try:
                        await ws.send_json(msg)
                    except Exception:
                        clients.discard(ws)

        async def clock() -> None:
            while True:
                await asyncio.sleep(0.05)
                playout.tick(0.05)

        tasks = [asyncio.create_task(broadcaster())]
        if tick:
            tasks.append(asyncio.create_task(clock()))
        yield
        for t in tasks:
            t.cancel()
        playout.stop()

    app = FastAPI(title="LeonRadio", version="0.1.0", lifespan=lifespan)
    app.state.host = host
    app.state.playout = playout

    @app.get("/api/info")
    def info() -> dict:
        return {"station": host.station, "config": host.config, "api_version": sdk.API_VERSION,
                "addons": [{"id": m.id, "name": m.name, "version": m.version,
                            "permissions": sorted(m.permissions)} for m in loaded]}

    @app.get("/api/audio")
    def audio_prefs() -> dict:
        """Para las preferencias: dispositivos disponibles, destinos y su elección actual."""
        from .engine import output as out

        try:
            devices, inputs = out.list_devices(), out.list_inputs()
        except Exception:  # noqa: BLE001 - sin PortAudio (p. ej. demostración): lista vacía
            devices, inputs = [], []
        info = host.state.get("audio.info") or {}
        return {"devices": devices, "inputs": inputs, "routes": info.get("routes", {}),
                "selected_inputs": host.state.get("audio.inputs") or {}, "simulated": info.get("simulated", True),
                "warnings": info.get("warnings", []), "active": info.get("device", "")}

    @app.get("/api/cover/{asset_id}")
    def cover(asset_id: int) -> Response:
        """Carátula incrustada del audio (solo por id de la biblioteca, nunca por ruta)."""
        try:
            path = playout._asset(asset_id)["path"]
        except ValueError as exc:
            raise HTTPException(404, "audio desconocido") from exc
        got = meta.read_cover(path) if path and not path.startswith("demo://") else None
        if got is None:
            raise HTTPException(404, "sin carátula")
        return Response(got[0], media_type=got[1], headers={"Cache-Control": "max-age=3600"})

    @app.get("/api/editors")
    def editors() -> list[dict]:
        return [{"id": e.id, "label": e.label, "icon": e.icon, "owner": owner}
                for e, owner, _ in host.editors.values()]

    @app.get("/api/editors/{editor_id}/draw")
    def draw(editor_id: str) -> dict:
        if editor_id not in host.editors:
            raise HTTPException(404, f"editor desconocido: {editor_id}")
        return host.draw_editor(editor_id)

    @app.post("/api/commands/{name}")
    def run(name: str, body: CommandBody | None = None) -> dict:
        if name not in host.commands:
            raise HTTPException(404, f"comando desconocido: {name}")
        try:
            result = host.run_command(name, (body.args if body else {}))
        except sdk.PermissionDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, RuntimeError, OSError, TypeError, KeyError) as exc:   # fallo explicable: se le dice al usuario
            logging.getLogger("leonradio").warning("comando %s falló: %s", name, exc)
            raise HTTPException(400, _friendly(exc)) from exc
        return {"ok": True, "result": result if isinstance(result, (str, int, float, bool, dict, list, type(None))) else None}

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        clients.add(sock)
        try:
            while True:
                await sock.receive_text()
        except WebSocketDisconnect:
            clients.discard(sock)

    ui = ui_dir or Path(os.environ.get("LEONRADIO_UI", REPO / "ui" / "src"))
    if ui.is_dir():
        # Cada arranque sirve la UI bajo una URL nueva (/v/<versión>/): el navegador nunca reutiliza
        # archivos viejos de una ejecución anterior, ni hace falta Ctrl+F5.
        ver = f"v{int(time.time())}"
        app.mount(f"/v/{ver}", NoCacheStatic(directory=ui, html=True), name="ui")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse(f"/v/{ver}/", status_code=307)

        # Compatibilidad: una página vieja en caché que pida /css/app.css o /js/main.js sigue funcionando
        app.mount("/", NoCacheStatic(directory=ui, html=True), name="ui-legacy")
    return app


def serve(library_dir: str | None, port: int = 8765, audio: str = "device", device: str | int | None = None,
          autoplay: bool | None = None) -> None:
    import socket

    import uvicorn

    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:
            print(f"\nYa hay algo escuchando en el puerto {port}.\n"
                  f"  · Si es LeonRadio, abre http://127.0.0.1:{port}/\n"
                  f"  · Si no, usa otro puerto:  leonradio serve --port {port + 1}\n")
            raise SystemExit(1)
    if library_dir and not Path(library_dir).is_dir():
        print(f"\nAVISO: la carpeta de la emisora no existe: {library_dir}\n"
              "       Arranco con la biblioteca vacía (verás datos de muestra).\n")
        library_dir = None
    logging.basicConfig(level=logging.INFO)
    app = create_app(library_dir=library_dir, audio=audio, device=device, autoplay=autoplay)
    out = app.state.playout.output
    print(f"\nAudio: {out.name}" + ("  (SIN dispositivo: todo es simulado)" if out.simulated else ""))
    if not out.simulated and not app.state.playout.autoplay:
        print("La emisión empieza en PAUSA: pulsa ▶ Reproducir en el panel Aire (o inicia con --autoplay).")
    print(f"\nLeonRadio listo en  http://127.0.0.1:{port}/   (Ctrl+C para detener)\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
