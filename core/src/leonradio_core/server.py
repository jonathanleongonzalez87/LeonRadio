"""Servidor: API REST + WebSocket de eventos + archivos de la UI.

    leonradio serve [--library CARPETA] [--port 8765]
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import addons, auth, backup, builtin, db, estaciones, library, meta, paths, sdk, security, settings
from .engine.monitor import MonitorHub
from .engine.output import make_output

log = logging.getLogger("leonradio.server")
REPO = Path(__file__).resolve().parents[3]  # <repo>/core/src/leonradio_core/server.py


class NoCacheStatic(StaticFiles):
    """Archivos de la UI siempre revalidados: al desarrollar, el navegador no se queda con versiones viejas."""

    async def get_response(self, path, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


LOST_KEY_HELP = (
    "  Anótala: no se puede ver otra vez. Si la pierdes, se crea una nueva desde este PC:\n"
    "    1. Abre una ventana de comandos en el PC.\n"
    "    2. Escribe  leonradio clave  y pulsa Enter.\n"
    "    3. Anota la clave nueva que aparece y úsala en los dispositivos.\n"
    "  Al crear una nueva, la anterior deja de valer en todos los dispositivos.")


class CommandBody(BaseModel):
    args: dict = {}


def _friendly(exc: Exception) -> str:
    """Mensaje corto para la interfaz (los errores de PortAudio traen códigos largos)."""
    text = sdk.safe_message(exc)
    if "PortAudio" in type(exc).__name__ or "host error" in text:
        return "Ese dispositivo no se pudo abrir (puede estar en uso, desconectado o no admitir el formato). Prueba otro de la lista o de otra interfaz."
    return text


def create_app(
    *, library_dir: str | None = None, db_path: str = ":memory:",
    addon_dirs: list[Path] | None = None, ui_dir: Path | None = None, tick: bool = True,
    audio: str = "null", device: str | int | None = None, autoplay: bool | None = None,
    require_auth: bool = False, strict_host: bool = False,
) -> FastAPI:
    """`require_auth` (modo red): hace falta la clave, salvo para el propio PC. `strict_host` (modo local): solo `Host` loopback."""
    if require_auth and not auth.current_hash():
        raise RuntimeError("falta la clave de acceso: ejecuta «leonradio clave»")
    paths.protect(db_path)                        # la base elegida con --db/LEONRADIO_DB tampoco se puede navegar
    host = sdk.Host(db_path=db_path)
    host.library_dir = library_dir
    scan_result = None
    if library_dir:
        try:
            scan_result = library.scan(
                host.db, library_dir, lock=host.db_lock,
                progress=lambda done, total: print(f"  Escaneando la biblioteca: {done}/{total}", flush=True)
                if done % 500 == 0 else None)
        except KeyboardInterrupt:                 # Ctrl+C durante el escaneo: lo ya guardado se conserva
            with host.db_lock:
                db.close(host.db)
            raise
    saved_routes = settings.load().get("audio", {}).get("routes", {})
    playout = builtin.register(host, output=make_output(audio, device, saved_routes), autoplay=autoplay)
    estaciones.register_all(host)
    roots = addon_dirs if addon_dirs is not None else [REPO / "addons"]
    env = os.environ.get("LEONRADIO_ADDONS")
    if env and addon_dirs is None:
        roots += [Path(p) for p in env.split(os.pathsep) if p]
    loaded = addons.discover(host, *roots)

    monitor = MonitorHub()
    playout.engine.taps.append(monitor.feed)
    clients: set[WebSocket] = set()
    limits = {"/ws": security.ConnectionLimit(security.MAX_WS_EVENTS),
              "/ws/monitor": security.ConnectionLimit(security.MAX_WS_MONITOR)}
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
        with host.db_lock:
            db.close(host.db)

    app = FastAPI(title="LeonRadio", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)    # nadie los usa: menos superficie
    app.add_middleware(security.SecurityMiddleware, strict_host=strict_host)
    app.state.auth = auth.AuthState(require_auth=require_auth)
    app.include_router(auth.build_router(lambda: host.station))

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.error("error inesperado en %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse({"detail": "Error interno"}, status_code=500)

    app.state.host = host
    app.state.scan = scan_result
    app.state.playout = playout

    @app.get("/api/info", dependencies=[Depends(auth.current_principal)])
    def info() -> dict:
        return {"station": host.station, "config": host.config, "api_version": sdk.API_VERSION,
                "addons": [{"id": m.id, "name": m.name, "version": m.version,
                            "permissions": sorted(m.permissions)} for m in loaded]}

    @app.get("/api/audio", dependencies=[Depends(auth.current_principal)])
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

    @app.get("/api/cover/{asset_id}", dependencies=[Depends(auth.current_principal)])
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

    @app.get("/api/editors", dependencies=[Depends(auth.current_principal)])
    def editors() -> list[dict]:
        return [{"id": e.id, "label": e.label, "icon": e.icon, "owner": owner, "station": e.station}
                for e, owner, _ in host.editors.values()]

    @app.get("/api/editors/{editor_id}/draw", dependencies=[Depends(auth.current_principal)])
    def draw(editor_id: str) -> dict:
        if editor_id not in host.editors:
            raise HTTPException(404, f"editor desconocido: {editor_id}")
        return host.draw_editor(editor_id)

    @app.post("/api/commands/{name}")
    def run(name: str, body: CommandBody | None = None, who: auth.Principal = Depends(auth.current_principal)) -> dict:
        if name not in host.commands:
            raise HTTPException(404, f"comando desconocido: {name}")
        try:
            result = host.run_command(name, (body.args if body else {}), principal=who.id)
        except sdk.PermissionDenied as exc:
            raise HTTPException(403, str(exc)) from exc
        except (ValueError, RuntimeError, OSError, TypeError, KeyError, OverflowError, UnicodeError, sqlite3.Error) as exc:
            # fallo explicable: se le dice al usuario (de la base nunca sale el texto SQL)
            msg = "No se pudo guardar el dato" if isinstance(exc, sqlite3.Error) else _friendly(exc)
            logging.getLogger("leonradio").warning("comando %s falló: %s", name, type(exc).__name__ if isinstance(exc, sqlite3.Error) else msg)
            raise HTTPException(400, msg) from exc
        return {"ok": True, "result": result if isinstance(result, (str, int, float, bool, dict, list, type(None))) else None}

    @app.get("/api/entities", dependencies=[Depends(auth.current_principal)])
    def entities_catalog() -> list[dict]:
        return host.entities.catalog()

    @app.get("/api/entities/{name}", dependencies=[Depends(auth.current_principal)])
    def entities_list(name: str, limit: int = 50, offset: int = 0, archived: bool = False) -> dict:
        try:
            return host.entities.list(name, limit=limit, offset=offset, include_archived=archived)
        except ValueError as exc:
            raise HTTPException(404, "entidad desconocida") from exc

    @app.get("/api/entities/{name}/{item_id}", dependencies=[Depends(auth.current_principal)])
    def entities_get(name: str, item_id: int) -> dict:
        try:
            return host.entities.get(name, item_id)
        except ValueError as exc:
            raise HTTPException(404, "no existe") from exc

    @app.websocket("/ws/monitor", dependencies=[Depends(auth.current_principal)])
    async def ws_monitor(sock: WebSocket) -> None:
        """Escucha remota: manda la mezcla principal en PCM de 16 bits (estéreo, 44,1 kHz) a este navegador."""
        from .engine.sources import SAMPLE_RATE

        if not limits["/ws/monitor"].acquire():
            await sock.close(code=1013)
            return
        await sock.accept()
        q: asyncio.Queue = asyncio.Queue()
        monitor.add(q, asyncio.get_running_loop())
        try:
            await sock.send_json({"rate": SAMPLE_RATE, "channels": 2})
            while True:
                await sock.send_bytes(await q.get())
        except Exception:  # noqa: BLE001 - el oyente se fue
            pass
        finally:
            monitor.remove(q)
            limits["/ws/monitor"].release()

    @app.websocket("/ws", dependencies=[Depends(auth.current_principal)])
    async def ws(sock: WebSocket) -> None:
        if not limits["/ws"].acquire():
            await sock.close(code=1013)
            return
        await sock.accept()
        clients.add(sock)
        try:
            while True:
                if len(await sock.receive_text()) > security.MAX_WS_MESSAGE:
                    await sock.close(code=1009)
                    break
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(sock)
            limits["/ws"].release()

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


def _lan_addresses() -> list[str]:
    """Direcciones IPv4 de este equipo en la red local (para decirle al usuario qué abrir desde otro dispositivo)."""
    import socket

    found: list[str] = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in found:
                found.append(ip)
    except OSError:
        pass
    return found


def serve(library_dir: str | None, port: int = 8765, audio: str = "device", device: str | int | None = None,
          autoplay: bool | None = None, host: str = "127.0.0.1", db_file: str | None = None) -> None:
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
    net = not paths.is_loopback(host)
    if net:                                       # modo red: sin clave no se arranca
        key = auth.ensure_key()
        if key:
            print("\n" + "=" * 56)
            print(f"  CLAVE DE ACCESO (se muestra una sola vez):  {key}")
            print("=" * 56)
            print(LOST_KEY_HELP)
    db_file = str(settings.db_path(db_file))
    print(f"\nBase de datos: {db_file}")
    backup.make_backup(db_file)                  # antes de abrir/migrar: así también queda copia previa a una migración
    try:
        app = create_app(library_dir=library_dir, db_path=db_file, audio=audio, device=device, autoplay=autoplay,
                         require_auth=net, strict_host=not net)
    except RuntimeError as exc:                   # p. ej. base creada por una versión más nueva
        print(f"\nERROR: {exc}\n")
        raise SystemExit(1)
    except sqlite3.DatabaseError as exc:
        print(f"\nERROR: no se pudo abrir la base de datos ({exc}). Restaura una copia de la carpeta «copias» "
              "(ver docs/arquitectura.md) o usa otra base con --db.\n")
        raise SystemExit(1)
    except KeyboardInterrupt:
        print("\nEscaneo cancelado: lo ya escaneado queda guardado; vuelve a arrancar para continuar.\n")
        raise SystemExit(130)
    if app.state.scan:
        s = app.state.scan
        print(f"Biblioteca: {s['added']} nuevas, {s['updated']} cambiadas, {s['retired']} retiradas, "
              f"{s['reactivated']} recuperadas, {s['unchanged']} sin cambios.")
    out = app.state.playout.output
    print(f"\nAudio: {out.name}" + ("  (SIN dispositivo: todo es simulado)" if out.simulated else ""))
    if not out.simulated and not app.state.playout.autoplay:
        print("La emisión empieza en PAUSA: pulsa ▶ Reproducir en el panel Aire (o inicia con --autoplay).")
    print(f"\nLeonRadio listo en  http://127.0.0.1:{port}/   (Ctrl+C para detener)")
    roots = ", ".join(n for n, _p in app.state.host.places())
    print(f"Carpetas permitidas para el Explorador: {roots or '(ninguna)'}  (más con: leonradio carpetas --agregar RUTA)")
    if net:
        for ip in _lan_addresses():
            print(f"  · Desde otro equipo de tu red:  http://{ip}:{port}/   (pide la clave de acceso)")
        print("  Acceso protegido con clave; el tráfico va sin cifrar: úsalo solo en una red de confianza.")
        print("  Este PC entra sin clave por http://127.0.0.1.")
    print()
    # proxy_headers=False: la IP del cliente es siempre la del socket (no se confía en X-Forwarded-For)
    uvicorn.run(app, host=host, port=port, log_level="info", ws_max_size=security.MAX_WS_MESSAGE, proxy_headers=False)
