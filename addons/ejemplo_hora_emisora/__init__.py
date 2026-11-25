"""Addon de ejemplo: un editor «Hora» con la hora de la emisora y un contador de emisiones.

Es la plantilla mínima de un addon: manifiesto + register()/unregister().
"""
from datetime import datetime, timezone, timedelta

import leonradio as lr

BOGOTA = timezone(timedelta(hours=-5))


class HoraEditor(lr.Editor):
    id = "ejemplo.hora"
    label = "Hora (ejemplo)"
    icon = "◔"

    def draw(self, ui, ctx):
        now = datetime.now(BOGOTA)
        ui.label("HORA DE LA EMISORA · Bogotá", "accent")
        ui.label(now.strftime("%H:%M:%S"), "big")
        ui.kv("Fecha", now.strftime("%Y-%m-%d"))
        ui.kv("Emisiones registradas (últimas 100)", len(ctx.recent_plays(100)))
        ui.kv("Veces pulsado", ctx.state.get("com.leonradio.ejemplo-hora.clicks", 0))
        ui.button("Pulsar", "ejemplo.pulsar")


@lr.command("ejemplo.pulsar")
def pulsar(ctx):
    n = ctx.state.get("com.leonradio.ejemplo-hora.clicks", 0) + 1
    ctx.set_state("clicks", n)
    return n


def register():
    lr.register_editor(HoraEditor)


def unregister():
    lr.unregister_editor(HoraEditor)
