"""Editores incluidos. Usan la misma API pública que cualquier addon (`leonradio_core.sdk`)."""

from __future__ import annotations

from .. import sdk
from ..uischema import UI
from .playout_demo import DemoPlayout


def _mmss(ms: int | float | None) -> str:
    if not ms:
        return "--:--"
    s = int(ms // 1000)
    return f"{s // 60:02d}:{s % 60:02d}"


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
        ui.progress(now["elapsed_ms"] / dur, f"{_mmss(now['elapsed_ms'])} / {_mmss(now['duration_ms'])}"
                    + ("  · EN PAUSA" if now.get("paused") else ""))
        with ui.row():
            ui.button("⏭ Siguiente", "playout.next")
            ui.button("⏯ Pausa", "playout.pause")


class ColaEditor(sdk.Editor):
    id, label, icon = "cola", "Cola", "☰"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        queue = ctx.state.get("playout.queue", [])
        ui.label(f"{len(queue)} elementos en cola", "muted")
        ui.table(["#", "Tipo", "Título", "Artista", "Dur."],
                 [[i + 1, q["kind"], q["title"], q.get("artist") or "", _mmss(q["duration_ms"])]
                  for i, q in enumerate(queue[:30])])


class HistorialEditor(sdk.Editor):
    id, label, icon = "historial", "Historial", "☷"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        plays = ctx.recent_plays(40)
        ui.label("Lo que sonó (UTC) · base de los reportes de derechos y compromisos", "muted")
        ui.table(["Inicio", "Tipo", "Título", "Artista", "Fuente", "Estado"],
                 [[p["started_at"][11:19], p["kind"], p["title"], p["artist"], p["source"], p["status"]]
                  for p in plays])


class VuEditor(sdk.Editor):
    id, label, icon = "vu", "VU", "◔"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
        ui.label("VU estéreo · niveles simulados", "warn")
        ui.custom("vu-meter")


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


class CartucheraEditor(sdk.Editor):
    id, label, icon = "cartuchera", "Cartuchera", "▦"

    def draw(self, ui: UI, ctx: sdk.Context) -> None:
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


def register(host: sdk.Host) -> DemoPlayout:
    sdk.bind(host)  # dueño «builtin», todos los permisos
    for cls in (AireEditor, ColaEditor, HistorialEditor, VuEditor, RelojEditor, DialEditor, CartucheraEditor):
        sdk.register_editor(cls)
    playout = DemoPlayout(host)
    host.register_command("playout.next", lambda ctx: playout.next("skipped"))
    host.register_command("playout.pause", lambda ctx: playout.toggle_pause())
    host.register_command("cart.fire", lambda ctx, asset_id: playout.fire_cart(int(asset_id)))
    playout.start()
    return playout
