"""Editores incluidos. Usan la misma API pública que cualquier addon (`leonradio_core.sdk`)."""

from __future__ import annotations

from .. import sdk
from ..uischema import UI
from .aux_demo import N_AUX, AuxDemo
from .playout_demo import DemoPlayout


def _mmss(ms: int | float | None) -> str:
    if not ms:
        return "--:--"
    s = int(ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


_STATUS = {"completed": "ok", "skipped": "saltada", "interrupted": "cortada", "failed": "falla"}
_KIND_LABEL = {"music": "Música", "jingle": "Jingles", "pisador": "Pisadores", "separador": "Separadores",
               "spot": "Cuñas", "voice": "Voces", "effect": "Efectos", "other": "Otros"}


class AireEditor(sdk.Editor):
    id, label, icon = "aire", "Aire", "●"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        now = ctx.state.get("playout.now")
        ui.label("SIMULADO · sin audio todavía", "warn")
        if not now:
            ui.label("Nada al aire", "muted")
            return
        ui.label(now["kind"].upper(), "accent")
        ui.label(now["title"], "big")
        ui.label(now.get("artist") or "", "muted")
        dur = max(now["duration_ms"], 1)
        with ui.row():
            ui.progress(now["elapsed_ms"] / dur, f"{_mmss(now['elapsed_ms'])} / {_mmss(now['duration_ms'])}"
                        + ("  · EN PAUSA" if now.get("paused") else ""))
            ui.button("⏭ Siguiente", "playout.next")
            ui.button("⏯ Pausa", "playout.pause")


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
        ui.label(f"{nxt['kind']} · {_mmss(nxt['duration_ms'])}"
                 + (f" · {nxt['artist']}" if nxt.get("artist") else ""), "muted")


class EmisionEditor(sdk.Editor):
    id, label, icon = "emision", "Emisión", "☰"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        queue = ctx.state.get("playout.queue", [])
        ui.label(f"{len(queue)} elementos en la emisión", "muted")
        ui.table(["#", "Tipo", "Título", "Artista", "Dur."],
                 [[i + 1, q["kind"], q["title"], q.get("artist") or "", _mmss(q["duration_ms"])]
                  for i, q in enumerate(queue[:30])], narrow_hide=[1, 3])


class HistorialEditor(sdk.Editor):
    id, label, icon = "historial", "Historial", "☷"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        plays = ctx.recent_plays(40)
        ui.label("Lo que sonó (UTC) · base de los reportes de derechos y compromisos", "muted")
        ui.table(["Inicio", "Tipo", "Título", "Artista", "Fuente", "Estado"],
                 [[p["started_at"][11:19], p["kind"], p["title"], p["artist"], p["source"],
                   _STATUS.get(p["status"], p["status"])] for p in plays], narrow_hide=[1, 3, 4])


class VuEditor(sdk.Editor):
    id, label, icon = "vu", "VU", "◔"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.custom("vu-meter", simulated=True)


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
        ui.label(f"Último: {last['title']}" if last else "F1–F12 o clic · simulado", "muted")
        ui.custom("cartwall", pads=pads, command="cart.fire")

    # -- pestaña Eventos ---------------------------------------------------
    def _events(self, ui: UI) -> None:
        ui.label("Eventos de ejemplo · la programación real llega en F3", "muted")
        ui.custom("event-list", events=sdk.load_json("events.json")["events"])

    # -- pestaña Explorador --------------------------------------------------
    def _explorer(self, ui: UI, ctx: sdk.Context) -> None:
        groups = ctx.library_groups()
        if not groups:
            ui.label("La biblioteca está vacía. Escanea una carpeta con `leonradio serve --library`.", "muted")
            return
        keyed = [(f"{g['kind']}|{g['decade'] or ''}", g) for g in groups]
        selected = ctx.state.get("explorer.group") or keyed[0][0]
        if selected not in dict(keyed):
            selected = keyed[0][0]
        with ui.row():
            for key, g in keyed:
                name = _KIND_LABEL.get(g["kind"], g["kind"]) + (f" {g['decade']}" if g["decade"] else "")
                ui.button(f"{name} ({g['n']})", "explorer.group", {"key": key}, size="sm", selected=key == selected)
        target = ctx.state.get("explorer.target", "emision")
        with ui.row():
            ui.label("Enviar a:", "muted")
            for t, name in [("emision", "Emisión")] + [(f"aux{n}", f"Aux {n}") for n in range(1, N_AUX + 1)]:
                ui.button(name, "explorer.target", {"target": t}, size="sm", selected=t == target)
        kind, decade = selected.split("|")
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
            ui.label(f"AUXILIAR {n} · simulado" + ("  · ▶ SONANDO" if st["playing"] else ""), "accent")
            ui.label(now["title"] if now else "Sin título", "title")
            dur = max(now["duration_ms"], 1) if now else 1
            el = now["elapsed_ms"] if now else 0
            ui.progress(el / dur, f"{_mmss(el) if now else '00:00'} / {_mmss(dur) if now else '00:00'}")
            with ui.row():
                for txt, cmd in (("▶", "aux.play"), ("⏸", "aux.pause"), ("⏹", "aux.stop"),
                                 ("⏭", "aux.next"), ("Vaciar", "aux.clear")):
                    ui.button(txt, cmd, {"n": n}, size="sm")
            q = st["queue"]
            if not q:
                ui.label("Lista vacía · agrega piezas desde Botonera ▸ Explorador (＋)", "muted")
            else:
                ui.table(["#", "Título", "Dur."], [[i + 1, x["title"], _mmss(x["duration_ms"])]
                                                  for i, x in enumerate(q[:40])])

    AuxEditor.__name__ = f"Aux{n}Editor"
    return AuxEditor


def register(host: sdk.Host) -> DemoPlayout:
    sdk.bind(host)  # dueño «builtin», todos los permisos
    for cls in (AireEditor, ProximaEditor, EmisionEditor, HistorialEditor, VuEditor, RelojEditor,
                DialEditor, BotoneraEditor, *[_aux_editor(n) for n in range(1, N_AUX + 1)]):
        sdk.register_editor(cls)

    playout = DemoPlayout(host)
    playout.aux = [AuxDemo(host, n) for n in range(1, N_AUX + 1)]
    host.register_command("playout.next", lambda ctx: playout.next("skipped"))
    host.register_command("playout.pause", lambda ctx: playout.toggle_pause())
    host.register_command("cart.fire", lambda ctx, asset_id: playout.fire_cart(int(asset_id)))
    host.register_command("explorer.group", lambda ctx, key: ctx.set_state("explorer.group", str(key)))
    host.register_command("explorer.target", lambda ctx, target: ctx.set_state("explorer.target", str(target)))
    host.register_command("list.add", lambda ctx, asset_id: playout.add_to(
        ctx.state.get("explorer.target", "emision"), int(asset_id)))
    for verb in ("play", "pause", "stop", "next", "clear"):
        host.register_command(f"aux.{verb}", lambda ctx, n, _v=verb: getattr(playout.aux[int(n) - 1], _v)())
    playout.start()
    return playout
