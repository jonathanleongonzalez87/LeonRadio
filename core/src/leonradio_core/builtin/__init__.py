"""Editores incluidos. Usan la misma API pública que cualquier addon (`leonradio_core.sdk`)."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .. import library, paths, sdk
from ..engine import files as F
from ..engine.output import NullOutput
from ..engine.playout import Playout
from ..uischema import UI

N_AUX = 4
FILE_LABEL = F.FILE_TYPES


def _station_tz(ctx: sdk.Context):
    """Zona horaria de la emisora; `None` si el sistema no trae la base de zonas (Windows sin `tzdata`): se usa la del equipo."""
    try:
        return ZoneInfo(ctx.config["timezone"])
    except Exception:  # noqa: BLE001
        return None


def _station_now(ctx: sdk.Context) -> datetime:
    """Hora de la emisora; si el sistema no trae la base de zonas horarias, la del equipo."""
    tz = _station_tz(ctx)
    return datetime.now(tz) if tz else datetime.now().astimezone()


def _local_hms(stamp: str, tz) -> str:
    """Hora (HH:MM:SS) de una marca ISO guardada en UTC, convertida a la hora de la emisora (`tz`; `None` = la del equipo)."""
    try:
        dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return stamp[11:19]


def _mmss(ms: int | float | None) -> str:
    if not ms:
        return "--:--"
    s = int(ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


def _dur(item: dict) -> str:
    """Duración visible: los audios y las pausas la tienen; los demás ficheros muestran un guion."""
    return _mmss(item["duration_ms"]) if item["file"] == F.AUDIO or item.get("kind") == "pause" else "—"


_STATUS = {"completed": "ok", "skipped": "saltada", "interrupted": "cortada", "failed": "falla"}
_KIND_LABEL = {"music": "Música", "jingle": "Jingles", "pisador": "Pisadores", "separador": "Separadores",
               "spot": "Cuñas", "voice": "Voces", "effect": "Efectos", "other": "Otros"}


def _file_list(ctx: sdk.Context, target: str, queue: list[dict]) -> dict:
    sel = ctx.state.get("list.selected") or {}
    return {"target": target, "uids": [q["uid"] for q in queue],
            "selected": sel.get("uid") if sel.get("target") == target else None}


def _file_row(i: int, q: dict) -> list:
    return [i + 1, FILE_LABEL.get(q["file"], q["file"]), q["kind"], q["title"], q.get("artist") or "", _dur(q)]


class AireEditor(sdk.Editor):
    id, label, icon = "aire", "Aire", "●"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        now = ctx.state.get("playout.now")
        info = ctx.state.get("audio.info") or {}
        playing = ctx.state.get("playout.playing", False)
        if info.get("simulated", True):
            ui.label("SIMULADO · sin salida de audio", "warn")
        else:
            ui.label(f"🔊 {info.get('device', '')}", "muted")
        if now:
            ui.label(f"{FILE_LABEL.get(now['file'], '').upper()} · {now['kind'].upper()}", "accent")
            ui.label(now["title"], "big")
            ui.label(now.get("artist") or "", "muted")
        else:
            ui.label("Nada al aire", "muted")
        dur = max((now or {}).get("duration_ms") or 1, 1)
        if now:
            ui.slider(now["elapsed_ms"], dur, "playout.seek", {}, suffix="" if playing else "  · EN PAUSA")
            left = max(0, dur - now["elapsed_ms"])
            ends = "—"
            if playing:
                ends = (_station_now(ctx) + timedelta(milliseconds=left)).strftime("%H:%M:%S")
            with ui.row(cls="right"):                      # debajo de la barra, alineado a la derecha
                ui.label("Tiempo restante", "muted")
                ui.label(_mmss(left) if left else "00:00", "mono")
                ui.label("·  Acaba a las", "muted")
                ui.label(ends, "mono")


class ControlesEditor(sdk.Editor):
    """Mandos de la Emisión: Play, Pausa, Stop y «parar después de la actual»."""

    id, label, icon = "controles", "Controles", "⏯"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        playing = ctx.state.get("playout.playing", False)
        paused = not playing and ctx.state.get("playout.now") is not None
        ui.custom("transport-deck", playing=playing, paused=paused, stop_after=ctx.state.get("playout.stop_after", False),
                  cmds={"play": "playout.play", "pause": "playout.pause_only", "stop": "playout.stop",
                        "next": "playout.next", "stop_after": "playout.stop_after"})


class MetadatosEditor(sdk.Editor):
    """Etiquetas del fichero elegido en la Emisión (o del que suena): carátula, intérprete, álbum…"""

    id, label, icon = "metadatos", "Metadatos", "🏷"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        info = ctx.state.get("meta.info")
        if not info:
            ui.label("Elige un fichero de la lista para ver sus metadatos", "muted")
            return
        ui.custom("tag-card", **info)


class ProximaEditor(sdk.Editor):
    id, label, icon = "proxima", "Próxima", "⏭"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        queue = ctx.state.get("playout.queue", [])
        ui.label("PRÓXIMA", "accent")
        if ctx.state.get("playout.stop_after"):          # «parar tras la actual»: no habrá siguiente
            ui.label("—", "title")
            ui.label("Parará al terminar la actual", "warn")
            return
        if not queue:
            ui.label("—", "title")
            return
        nxt = queue[0]
        ui.label(nxt["title"], "title")
        ui.label(f"{FILE_LABEL.get(nxt['file'], '')} · {nxt['kind']} · {_dur(nxt)}"
                 + (f" · {nxt['artist']}" if nxt.get("artist") else ""), "muted")


class EmisionEditor(sdk.Editor):
    id, label, icon = "emision", "Emisión", "☰"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        queue = ctx.state.get("playout.queue", [])
        total = ctx.state.get("playout.queue_total", len(queue))
        ui.label(f"{total} ficheros en la emisión (audios, eventos y otros)"
                 + (f" · se muestran {len(queue)}" if total > len(queue) else ""), "muted")
        msg = ctx.state.get("playout.message")
        if msg:
            ui.label(msg, "warn")
        with ui.row():
            ui.button("Vaciar", "playout.clear", size="sm")
        ui.table(["#", "Fichero", "Tipo", "Título", "Artista", "Dur."],
                 [_file_row(i, q) for i, q in enumerate(queue[:60])], narrow_hide=[2, 4],
                 file_list=_file_list(ctx, "emision", queue[:60]))


class HistorialEditor(sdk.Editor):
    id, label, icon = "historial", "Historial", "☷"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        plays = ctx.recent_plays(40)
        tz = _station_tz(ctx)
        ui.label("Lo que sonó (hora de la emisora) · base de los reportes de derechos y compromisos", "muted")
        ui.table(["Inicio", "Fichero", "Tipo", "Título", "Artista", "Fuente", "Estado"],
                 [[_local_hms(p["started_at"], tz), FILE_LABEL.get(p["file_type"], p["file_type"]), p["kind"], p["title"],
                   p["artist"], p["source"], _STATUS.get(p["status"], p["status"])] for p in plays],
                 narrow_hide=[2, 4, 5])


class VuEditor(sdk.Editor):
    id, label, icon = "vu", "VU", "◔"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.custom("vu-meter", simulated=(ctx.state.get("audio.info") or {}).get("simulated", True))


class RelojEditor(sdk.Editor):
    id, label, icon = "reloj", "Reloj", "◷"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.custom("analog-clock", timezone=ctx.config["timezone"], name=ctx.config["short"])


class DialEditor(sdk.Editor):
    id, label, icon = "dial", "Dial / RDS", "◉"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        now = ctx.state.get("playout.now") or {}
        rds = " – ".join(x for x in (now.get("artist"), now.get("title")) if x) or ctx.config["name"]
        ui.custom("fm-dial", name=ctx.config["short"], frequency=ctx.config.get("frequency"), rds=rds)


class BotoneraEditor(sdk.Editor):
    """Botonera (pads 1–0 del teclado numérico) con las pestañas Eventos y Explorador."""

    id, label, icon = "botonera", "Botonera", "▦"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        self._pads(ui, ctx)

    # -- pestaña Botonera --------------------------------------------------
    def _pads(self, ui: UI, ctx: sdk.Context) -> None:
        cfg = sdk.load_json("cartwall.json")
        pieces: list[dict] = []
        for kind in cfg["kinds"]:
            pieces += ctx.library(kind, limit=cfg["pads"])
        pads = [{"key": str((i + 1) % 10), "asset_id": p["id"], "title": p["title"],
                 "sub": p["kind"], "style": cfg["styles"].get(p["kind"], "graphite")}
                for i, p in enumerate(pieces[: cfg["pads"]])]
        last = ctx.state.get("cart.last")
        ui.label(f"Último: {last['title']}" if last else "teclado numérico 1–0 o clic · suena sobre la emisión", "muted")
        ui.custom("cartwall", pads=pads, command="cart.fire", active=ctx.state.get("cart.active", []))

    # -- pestaña Eventos (programados) -------------------------------------------
    def _events(self, ui: UI) -> None:
        ui.label("Eventos de ejemplo · la programación real llega en F3", "muted")
        ui.custom("event-list", events=sdk.load_json("events.json")["events"])

    # -- pestaña Explorador --------------------------------------------------------
    def _explorer(self, ui: UI, ctx: sdk.Context) -> None:
        mode = ctx.state.get("explorer.mode", "lib")
        with ui.row():
            ui.button("Biblioteca", "explorer.mode", {"mode": "lib"}, size="sm", selected=mode == "lib")
            ui.button("Mi equipo", "explorer.mode", {"mode": "disk"}, size="sm", selected=mode == "disk")
            ui.label("Enviar a:", "muted")
            target = ctx.state.get("explorer.target", "emision")
            for t, name in [("emision", "Emisión")] + [(f"aux{n}", f"Aux {n}") for n in range(1, N_AUX + 1)]:
                ui.button(name, "explorer.target", {"target": t}, size="sm", selected=t == target)
        if mode == "disk":
            _disk(ui, ctx)
            return
        groups = ctx.library_groups()
        keyed: list[tuple[str, str]] = [
            (f"{g['kind']}|{g['decade'] or ''}",
             f"{_KIND_LABEL.get(g['kind'], g['kind'])}{' ' + g['decade'] if g['decade'] else ''} ({g['n']})")
            for g in groups]
        tpl = F.templates()
        keyed.append(("event|", f"Eventos ({sum(t['file'] == F.EVENT for t in tpl)})"))
        keyed.append(("other|", f"Otros ({sum(t['file'] == F.OTHER for t in tpl)})"))
        lists = ctx.playlists()
        if lists:
            keyed.append(("m3u|", f"Listas ({len(lists)})"))
        selected = ctx.state.get("explorer.group") or keyed[0][0]
        if selected not in dict(keyed):
            selected = keyed[0][0]
        with ui.row():
            for key, label in keyed:
                ui.button(label, "explorer.group", {"key": key}, size="sm", selected=key == selected)

        kind, decade = selected.split("|")
        if kind in (F.EVENT, F.OTHER):                       # plantillas de ficheros que no son audio
            for t in (t for t in tpl if t["file"] == kind):
                with ui.row(cls="item"):
                    ui.label(t["title"])
                    ui.label(t["type"], "muted")
                    ui.label(_dur({"file": t["file"], "kind": t["type"],
                                   "duration_ms": float(t.get("params", {}).get("seconds", 0)) * 1000}), "mono")
                    ui.button("＋", "list.add", {"template": t["key"]}, size="sm")
        elif kind == "m3u":                                  # listas .m3u de la carpeta de la emisora
            for pl in lists:
                with ui.row(cls="item"):
                    ui.label(pl["name"])
                    ui.label(".m3u", "muted")
                    ui.button("Cargar", "list.load_m3u", {"path": pl["path"]}, size="sm")
        else:
            for it in ctx.library(kind, decade=decade or None, limit=80):
                with ui.row(cls="item"):
                    ui.label(it["title"])
                    ui.label(it["artist"] or "", "muted")
                    ui.label(_mmss(it["duration_ms"]), "mono")
                    ui.button("＋", "list.add", {"asset_id": it["id"]}, size="sm")


def _disk(ui: UI, ctx: sdk.Context) -> None:
    """Navegador del disco dentro del panel: solo los lugares permitidos, con sus carpetas y audios con «＋»."""
    places = ctx._host.places()
    if not places:
        ui.label("No hay carpetas permitidas. Agrega una con  leonradio carpetas --agregar RUTA", "warn")
        return
    try:                                                   # estado viejo o fuera de la lista: vuelve a la primera
        path = ctx.safe_path(ctx.state.get("explorer.path") or "", "dir")
    except ValueError:
        path = places[0][1]
    with ui.row():
        for name, p in places:
            ui.button(name, "explorer.cd", {"path": str(p)}, size="sm", selected=p == path)
    with ui.row():
        if path not in [p for _n, p in places]:
            ui.button("⬆ Subir", "explorer.cd", {"path": str(path.parent)}, size="sm")
        ui.label(str(path), "mono")
    try:
        entries = sorted(os.scandir(path), key=lambda e: e.name.lower())
    except OSError as exc:
        ui.label(f"No se puede abrir esta carpeta: {exc.strerror or exc}", "warn")
        return
    dirs = [e for e in entries if e.is_dir() and not e.name.startswith((".", "$"))]
    audio = [e for e in entries if e.is_file() and Path(e.name).suffix.lower() in library.AUDIO_EXT]
    if audio:
        ui.button(f"＋ Agregar los {len(audio)} audios de esta carpeta", "explorer.add_folder", {"path": str(path)}, size="sm")
    for e in dirs[:150]:
        with ui.row(cls="item"):
            ui.button(f"📁 {e.name}", "explorer.cd", {"path": e.path}, size="sm")
    for e in audio[:200]:
        with ui.row(cls="item"):
            ui.label(Path(e.name).stem)
            ui.button("＋", "list.add_path", {"path": e.path}, size="sm")
    if not dirs and not audio:
        ui.label("Carpeta sin subcarpetas ni audios compatibles", "muted")
    elif len(dirs) > 150 or len(audio) > 200:
        ui.label("Se muestran las primeras entradas de la carpeta", "muted")


class EventosEditor(sdk.Editor):
    id, label, icon = "eventos", "Eventos", "⏱"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        BotoneraEditor._events(None, ui)


class ExploradorEditor(sdk.Editor):
    id, label, icon = "explorador", "Explorador", "🗂"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        BotoneraEditor._explorer(None, ui, ctx)


class NavegadorEditor(sdk.Editor):
    """Navegador web propio: sitios dentro del automatizador (también suenan: streams, radios en línea…)."""

    id, label, icon = "navegador", "Navegador", "🌐"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.custom("web-browser", id="nav", home=ctx.config.get("website") or "")


def _hms(s: int) -> str:
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


_STREAM_STATE = {"stopped": ("FUERA DEL AIRE", "muted"), "connecting": ("CONECTANDO…", "warn"),
                 "live": ("● EN EL AIRE", "ok"), "reconnecting": ("RECONECTANDO…", "warn"), "error": ("ERROR", "warn")}


class StreamingEditor(sdk.Editor):
    """Transmisión a un servidor Icecast (como BUTT): envía la mezcla principal en MP3 y puede grabarla."""

    id, label, icon = "streaming", "Streaming", "📡"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        st = ctx.state.get("stream.status") or {"state": "stopped", "message": "", "seconds": 0, "kb": 0,
                                                "recording": False, "record_path": "", "song": ""}
        cfg = ctx.state.get("stream.config") or {}
        with ui.tabs("stream") as t:
            with t.tab("Transmisión"):
                text, tone = _STREAM_STATE.get(st["state"], ("—", "muted"))
                ui.label(text, tone if tone != "ok" else "ok")
                if st["message"]:
                    ui.label(st["message"], "warn" if st["state"] in ("error", "reconnecting") else "muted")
                live = st["state"] in ("live", "connecting", "reconnecting")
                with ui.row():
                    if live:
                        ui.button("■ Desconectar", "stream.disconnect", selected=True)
                    else:
                        ui.button("● Conectar", "stream.connect")
                    ui.button("⏹ Detener grabación" if st["recording"] else "⏺ Grabar a archivo", "stream.record",
                              selected=st["recording"])
                ui.kv("Tiempo al aire", _hms(st["seconds"]))
                ui.kv("Enviado", f"{st['kb'] / 1024:.2f} MB")
                ui.kv("Formato", f"MP3 · {cfg.get('bitrate', 128)} kbps · 44,1 kHz · estéreo")
                ui.kv("Sonando", st["song"] or "—")
                if st["recording"]:
                    ui.label(f"Grabando en: {st['record_path']}", "muted")
                ui.label("Transmite lo mismo que sale por la salida principal (con pisadores y todo).", "muted")
            with t.tab("Servidor"):
                ui.label("Icecast 2 (servidor de streaming). Los cambios se guardan al salir de cada campo.", "muted")
                ui.form("stream.set", [
                    {"key": "host", "label": "Dirección", "kind": "text", "value": cfg.get("host", ""),
                     "placeholder": "stream.miemisora.com"},
                    {"key": "port", "label": "Puerto", "kind": "number", "value": cfg.get("port", 8000)},
                    {"key": "mount", "label": "Punto de montaje", "kind": "text", "value": cfg.get("mount", "/stream")},
                    {"key": "user", "label": "Usuario", "kind": "text", "value": cfg.get("user", "source")},
                    {"key": "password", "label": "Contraseña", "kind": "password", "value": "",
                     "placeholder": "guardada (escribe para cambiarla)" if cfg.get("has_password") else "contraseña de la fuente"},
                    {"key": "tls", "label": "Conexión segura (TLS)", "kind": "check", "value": bool(cfg.get("tls"))},
                    {"key": "reconnect", "label": "Reconectar automáticamente", "kind": "check",
                     "value": bool(cfg.get("reconnect", True))},
                ])
            with t.tab("Emisora"):
                ui.form("stream.set", [
                    {"key": "name", "label": "Nombre", "kind": "text", "value": cfg.get("name", "")},
                    {"key": "description", "label": "Descripción", "kind": "text", "value": cfg.get("description", "")},
                    {"key": "genre", "label": "Género", "kind": "text", "value": cfg.get("genre", "")},
                    {"key": "url", "label": "Sitio web", "kind": "text", "value": cfg.get("url", "")},
                    {"key": "public", "label": "Listar en directorios públicos", "kind": "check", "value": bool(cfg.get("public"))},
                    {"key": "bitrate", "label": "Calidad (kbps)", "kind": "select", "value": str(cfg.get("bitrate", 128)),
                     "options": ["64", "96", "128", "160", "192", "256", "320"]},
                    {"key": "record_dir", "label": "Carpeta de grabaciones", "kind": "text", "value": cfg.get("record_dir", ""),
                     "placeholder": "Música\\LeonRadio grabaciones (por defecto)"},
                ])


class MonitoresEditor(sdk.Editor):
    """Escuchar la emisión desde este dispositivo (teléfono, tableta…) con monitores y perilla de volumen."""

    id, label, icon = "monitores", "Monitores", "🔊"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.custom("monitors")


VARIOS_DEFAULT = ["botonera", "eventos", "explorador", "navegador", "streaming", "monitores"]


class VariosEditor(sdk.Editor):
    """Panel que acopla otros paneles por pestañas (Botonera, Eventos, Explorador, Metadatos, Historial…)."""

    id, label, icon = "varios", "Varios", "🗃"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        names = {e.id: e for e, _o, _p in ctx._host.editors.values()}
        tabs = [t for t in (ctx.state.get("varios.tabs") or VARIOS_DEFAULT) if t in names and t != "varios"]
        with ui.tabs("varios") as t:
            for eid in tabs:
                with t.tab(names[eid].label):
                    ui._add(ctx.draw_editor(eid))
                    ui.separator()
                    ui.button("✕ Quitar esta pestaña", "varios.remove", {"editor": eid}, size="sm")
            with t.tab("＋"):
                ui.label("Acoplar otro panel a este", "muted")
                for eid, e in names.items():
                    if eid != "varios" and eid not in tabs:
                        ui.button(f"{e.icon} {e.label}", "varios.add", {"editor": eid}, size="sm")


def _aux_editor(n: int) -> type[sdk.Editor]:
    class AuxEditor(sdk.Editor):
        id, label, icon = f"aux{n}", f"Auxiliar {n}", "♫"

        def draw(self, ui: UI, ctx: sdk.Context) -> None:
            st = ctx.state.get(f"aux.{n}") or {"now": None, "queue": [], "playing": False}
            now = st["now"]
            ui.label(f"AUXILIAR {n}" + ("  · ▶ SONANDO" if st["playing"] else ""), "accent")
            ui.label(now["title"] if now else "Sin título", "title")
            if now:
                dur = max(now["duration_ms"], 1)
                ui.label(f"{FILE_LABEL.get(now['file'], '')} · {now['kind']}", "muted")
                ui.slider(now["elapsed_ms"], dur, "aux.seek", {"n": n})
            else:
                ui.progress(0, "00:00 / 00:00")
            ui.custom("transport-deck", playing=st["playing"], paused=not st["playing"] and now is not None,
                      stop_after=st.get("stop_after", False), args={"n": n},
                      cmds={"play": "aux.play", "pause": "aux.pause", "stop": "aux.stop", "next": "aux.next",
                            "stop_after": "aux.stop_after"})
            nxt = None if st.get("stop_after") else (st["queue"][0] if st["queue"] else None)
            ui.label("Próxima: " + (nxt["title"] if nxt else ("— (parará al terminar)" if st.get("stop_after") else "—")), "muted")
            with ui.row():
                ui.button("Vaciar", "aux.clear", {"n": n}, size="sm")
            q = st["queue"]
            if not q:
                ui.label("Lista vacía · agrega ficheros desde Botonera ▸ Explorador (＋)", "muted")
            else:
                ui.table(["#", "Fichero", "Título", "Dur."],
                         [[i + 1, FILE_LABEL.get(x["file"], x["file"]), x["title"], _dur(x)]
                          for i, x in enumerate(q[:40])], narrow_hide=[1],
                         file_list=_file_list(ctx, f"aux{n}", q[:40]))

    AuxEditor.__name__ = f"Aux{n}Editor"
    return AuxEditor


# Nivel de cada comando incluido (S7 asigna permisos por nivel). Un comando nuevo sin nivel aquí hace fallar una prueba.
RISK = {
    "emision": ("playout.next", "playout.pause", "playout.play", "playout.pause_only", "playout.stop", "playout.stop_after",
                "playout.clear", "playout.seek", "aux.seek", "aux.play", "aux.pause", "aux.stop", "aux.next",
                "aux.stop_after", "aux.clear", "cart.fire", "stream.connect", "stream.disconnect", "stream.record",
                "list.add", "list.remove", "list.move", "list.move_to"),
    "config": ("stream.set", "audio.set_route", "audio.set_input", "audio.test"),
    "archivos": ("explorer.cd", "list.add_path", "explorer.add_folder", "list.load_m3u"),
    "normal": ("list.select", "explorer.group", "explorer.target", "explorer.mode", "varios.add", "varios.remove"),
}
RISK = {name: level for level, names in RISK.items() for name in names}


def register(host: sdk.Host, output=None, autoplay: bool | None = None) -> Playout:
    """Registra los editores y comandos incluidos y arranca el Playout.

    `output`: salida de audio (por defecto la nula: nada suena). `autoplay`: empezar a reproducir la Emisión
    al arrancar (por defecto sí con salida nula; con salida real hay que pedirlo, para que no suene de golpe).
    """
    sdk.bind(host)  # dueño «builtin», todos los permisos
    for cls in (AireEditor, ControlesEditor, MetadatosEditor, ProximaEditor, EmisionEditor, HistorialEditor, VuEditor, RelojEditor,
                DialEditor, BotoneraEditor, EventosEditor, ExploradorEditor, NavegadorEditor, StreamingEditor, MonitoresEditor, VariosEditor, *[_aux_editor(n) for n in range(1, N_AUX + 1)]):
        sdk.register_editor(cls)

    output = output or NullOutput()
    playout = Playout(host, output, autoplay=output.simulated if autoplay is None else autoplay)

    def target(ctx: sdk.Context) -> str:
        return ctx.state.get("explorer.target", "emision")

    host.register_command("audio.set_route", lambda ctx, dest, device=None: playout.set_route(str(dest), device))
    host.register_command("audio.set_input", lambda ctx, line, device=None: playout.set_input(str(line), device))

    def _test(ctx: sdk.Context, device: str | None = None) -> dict:
        from ..engine.output import test_tone

        return {"device": test_tone(device or None)}

    host.register_command("audio.test", _test)
    def _stream_set(ctx: sdk.Context, **fields) -> dict:
        folder = str(fields.get("record_dir") or "").strip()
        if folder:                                             # se guarda ya resuelta; la carpeta puede no existir aún
            p = ctx.safe_path(folder, create_ok=True)
            if p.exists() and not p.is_dir():
                raise ValueError("no es una carpeta")
            fields["record_dir"] = str(p)
        return playout.stream_set(**fields)

    playout.stream.record_check = lambda folder: sdk.Context(host, "builtin", frozenset()).safe_path(folder, create_ok=True)
    host.register_command("stream.set", _stream_set)
    for verb in ("connect", "disconnect", "record"):
        host.register_command(f"stream.{verb}", lambda ctx, _v=verb: playout.stream_do(_v))
    host.register_command("playout.next", lambda ctx: playout.transport("emision", "next"))
    host.register_command("playout.pause", lambda ctx: playout.transport("emision", "toggle"))
    host.register_command("playout.play", lambda ctx: playout.transport("emision", "play"))
    host.register_command("playout.pause_only", lambda ctx: playout.transport("emision", "pause"))
    host.register_command("playout.stop", lambda ctx: playout.transport("emision", "stop"))
    host.register_command("playout.stop_after", lambda ctx: playout.transport("emision", "stop_after"))
    host.register_command("list.select", lambda ctx, target, uid: playout.select(str(target), str(uid)))
    host.register_command("list.move_to", lambda ctx, target, uid, index: playout.move_to(
        str(target), str(uid), int(index)))
    host.register_command("playout.clear", lambda ctx: playout.clear("emision"))
    host.register_command("cart.fire", lambda ctx, asset_id: playout.fire_cart(int(asset_id)))
    host.register_command("explorer.group", lambda ctx, key: ctx.set_state("explorer.group", str(key)))
    host.register_command("explorer.target", lambda ctx, target: ctx.set_state("explorer.target", str(target)))
    host.register_command("list.add", lambda ctx, asset_id=None, template=None: playout.add_to(
        target(ctx), template if template else int(asset_id)))
    host.register_command("playout.seek", lambda ctx, ms: playout.seek("emision", float(ms)))
    host.register_command("aux.seek", lambda ctx, n, ms: playout.seek(f"aux{int(n)}", float(ms)))
    host.register_command("explorer.mode", lambda ctx, mode: ctx.set_state("explorer.mode", "disk" if mode == "disk" else "lib"))

    host.register_command("explorer.cd", lambda ctx, path: ctx.set_state("explorer.path", str(ctx.safe_path(path, "dir"))))
    host.register_command("list.add_path", lambda ctx, path: playout.add_path(target(ctx), str(ctx.safe_path(path, "file"))))
    host.register_command("explorer.add_folder", lambda ctx, path: playout.add_folder(target(ctx), str(ctx.safe_path(path, "dir"))))

    def _varios(ctx: sdk.Context, editor: str, add: bool) -> None:
        tabs = list(ctx.state.get("varios.tabs") or VARIOS_DEFAULT)
        if add and editor not in tabs:
            tabs.append(editor)
        if not add and editor in tabs:
            tabs.remove(editor)
        ctx.set_state("varios.tabs", tabs)

    host.register_command("varios.add", lambda ctx, editor: _varios(ctx, str(editor), True))
    host.register_command("varios.remove", lambda ctx, editor: _varios(ctx, str(editor), False))
    def _load_m3u(ctx: sdk.Context, path: str) -> dict:
        if not host.library_dir:
            raise ValueError("la lista debe estar dentro de la carpeta de la emisora")
        p = paths.check(str(path), [Path(host.library_dir)], must="file")     # solo la biblioteca, como antes
        if p.suffix.lower() not in (".m3u", ".m3u8"):
            raise ValueError("no es una lista .m3u")
        return playout.load_m3u(target(ctx), str(p))

    host.register_command("list.load_m3u", _load_m3u)
    for verb in ("play", "pause", "stop", "next"):
        host.register_command(f"aux.{verb}", lambda ctx, n, _v=verb: playout.transport(f"aux{int(n)}", _v))
    host.register_command("list.remove", lambda ctx, target, uid: playout.remove(str(target), str(uid)))
    host.register_command("list.move", lambda ctx, target, uid, delta: playout.move(str(target), str(uid), int(delta)))
    host.register_command("aux.stop_after", lambda ctx, n: playout.transport(f"aux{int(n)}", "stop_after"))
    host.register_command("aux.clear", lambda ctx, n: playout.clear(f"aux{int(n)}"))
    for name, (_fn, owner, _perms) in host.commands.items():
        if owner == "builtin":
            host.command_risk[name] = RISK.get(name, "normal")
    playout.start()
    return playout
