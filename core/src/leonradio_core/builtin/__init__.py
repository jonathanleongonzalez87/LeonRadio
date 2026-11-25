"""Editores incluidos. Usan la misma API pública que cualquier addon (`leonradio_core.sdk`)."""

from __future__ import annotations

from .. import sdk
from ..engine import files as F
from ..engine.output import NullOutput
from ..engine.playout import Playout
from ..uischema import UI

N_AUX = 4
FILE_LABEL = F.FILE_TYPES


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
        with ui.row():
            if now:
                ui.progress(now["elapsed_ms"] / dur, f"{_mmss(now['elapsed_ms'])} / {_mmss(now['duration_ms'])}"
                            + ("" if playing else "  · EN PAUSA"))
            ui.button("⏭ Siguiente", "playout.next")
            ui.button("⏸ Pausa" if playing else "▶ Reproducir", "playout.pause")


class ProximaEditor(sdk.Editor):
    id, label, icon = "proxima", "Próxima", "⏭"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        queue = ctx.state.get("playout.queue", [])
        ui.label("PRÓXIMA", "accent")
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
                 [_file_row(i, q) for i, q in enumerate(queue[:60])], narrow_hide=[2, 4])


class HistorialEditor(sdk.Editor):
    id, label, icon = "historial", "Historial", "☷"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        plays = ctx.recent_plays(40)
        ui.label("Lo que sonó (UTC) · base de los reportes de derechos y compromisos", "muted")
        ui.table(["Inicio", "Fichero", "Tipo", "Título", "Artista", "Fuente", "Estado"],
                 [[p["started_at"][11:19], FILE_LABEL.get(p["file_type"], p["file_type"]), p["kind"], p["title"],
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
    """Botonera (pads F1–F12) con las pestañas Eventos y Explorador."""

    id, label, icon = "botonera", "Botonera", "▦"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        with ui.tabs("botonera") as tabs:
            with tabs.tab("Botonera"):
                self._pads(ui, ctx)
            with tabs.tab("Eventos"):
                self._events(ui)
            with tabs.tab("Explorador"):
                self._explorer(ui, ctx)

    # -- pestaña Botonera --------------------------------------------------
    def _pads(self, ui: UI, ctx: sdk.Context) -> None:
        cfg = sdk.load_json("cartwall.json")
        pieces: list[dict] = []
        for kind in cfg["kinds"]:
            pieces += ctx.library(kind, limit=cfg["pads"])
        pads = [{"key": f"F{i + 1}", "asset_id": p["id"], "title": p["title"],
                 "sub": p["kind"], "style": cfg["styles"].get(p["kind"], "graphite")}
                for i, p in enumerate(pieces[: cfg["pads"]])]
        last = ctx.state.get("cart.last")
        ui.label(f"Último: {last['title']}" if last else "F1–F12 o clic · suena sobre la emisión", "muted")
        ui.custom("cartwall", pads=pads, command="cart.fire")

    # -- pestaña Eventos (programados) -------------------------------------------
    def _events(self, ui: UI) -> None:
        ui.label("Eventos de ejemplo · la programación real llega en F3", "muted")
        ui.custom("event-list", events=sdk.load_json("events.json")["events"])

    # -- pestaña Explorador --------------------------------------------------------
    def _explorer(self, ui: UI, ctx: sdk.Context) -> None:
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
        target = ctx.state.get("explorer.target", "emision")
        with ui.row():
            ui.label("Enviar a:", "muted")
            for t, name in [("emision", "Emisión")] + [(f"aux{n}", f"Aux {n}") for n in range(1, N_AUX + 1)]:
                ui.button(name, "explorer.target", {"target": t}, size="sm", selected=t == target)

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
                ui.progress(now["elapsed_ms"] / dur, f"{_mmss(now['elapsed_ms'])} / {_mmss(dur)}")
            else:
                ui.progress(0, "00:00 / 00:00")
            with ui.row():
                for txt, cmd in (("▶", "aux.play"), ("⏸", "aux.pause"), ("⏹", "aux.stop"),
                                 ("⏭", "aux.next"), ("Vaciar", "aux.clear")):
                    ui.button(txt, cmd, {"n": n}, size="sm")
            q = st["queue"]
            if not q:
                ui.label("Lista vacía · agrega ficheros desde Botonera ▸ Explorador (＋)", "muted")
            else:
                ui.table(["#", "Fichero", "Título", "Dur."],
                         [[i + 1, FILE_LABEL.get(x["file"], x["file"]), x["title"], _dur(x)]
                          for i, x in enumerate(q[:40])], narrow_hide=[1])

    AuxEditor.__name__ = f"Aux{n}Editor"
    return AuxEditor


def register(host: sdk.Host, output=None, autoplay: bool | None = None) -> Playout:
    """Registra los editores y comandos incluidos y arranca el Playout.

    `output`: salida de audio (por defecto la nula: nada suena). `autoplay`: empezar a reproducir la Emisión
    al arrancar (por defecto sí con salida nula; con salida real hay que pedirlo, para que no suene de golpe).
    """
    sdk.bind(host)  # dueño «builtin», todos los permisos
    for cls in (AireEditor, ProximaEditor, EmisionEditor, HistorialEditor, VuEditor, RelojEditor,
                DialEditor, BotoneraEditor, *[_aux_editor(n) for n in range(1, N_AUX + 1)]):
        sdk.register_editor(cls)

    output = output or NullOutput()
    playout = Playout(host, output, autoplay=output.simulated if autoplay is None else autoplay)

    def target(ctx: sdk.Context) -> str:
        return ctx.state.get("explorer.target", "emision")

    host.register_command("playout.next", lambda ctx: playout.transport("emision", "next"))
    host.register_command("playout.pause", lambda ctx: playout.transport("emision", "toggle"))
    host.register_command("playout.play", lambda ctx: playout.transport("emision", "play"))
    host.register_command("playout.clear", lambda ctx: playout.clear("emision"))
    host.register_command("cart.fire", lambda ctx, asset_id: playout.fire_cart(int(asset_id)))
    host.register_command("explorer.group", lambda ctx, key: ctx.set_state("explorer.group", str(key)))
    host.register_command("explorer.target", lambda ctx, target: ctx.set_state("explorer.target", str(target)))
    host.register_command("list.add", lambda ctx, asset_id=None, template=None: playout.add_to(
        target(ctx), template if template else int(asset_id)))
    host.register_command("list.load_m3u", lambda ctx, path: playout.load_m3u(target(ctx), str(path)))
    for verb in ("play", "pause", "stop", "next"):
        host.register_command(f"aux.{verb}", lambda ctx, n, _v=verb: playout.transport(f"aux{int(n)}", _v))
    host.register_command("aux.clear", lambda ctx, n: playout.clear(f"aux{int(n)}"))
    playout.start()
    return playout
