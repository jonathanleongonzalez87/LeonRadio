"""Entidades anteriores al marco, solo lectura: su tabla la escribe `playlog.py` (Compromiso pasó a Producción en A6)."""

from .entities import Entity, Field

EMISION = Entity(
    "emision", "playlog", owner="al_aire", label="Registro de emisión", about="Qué sonó, cuándo y por dónde",
    title="title", managed=False,
    fields=(Field("started_at", "datetime"), Field("kind"), Field("title"), Field("artist"), Field("source"),
            Field("status"), Field("asset_id", "int", ref="pieza")))
