"""Entidades anteriores al marco, solo lectura: sus tablas las escriben `playlog.py` y el código de A6 hasta rediseñarlas."""

from .entities import Entity, Field

EMISION = Entity(
    "emision", "playlog", owner="al_aire", label="Registro de emisión", about="Qué sonó, cuándo y por dónde",
    title="title", managed=False,
    fields=(Field("started_at", "datetime"), Field("kind"), Field("title"), Field("artist"), Field("source"),
            Field("status"), Field("asset_id", "int", ref="pieza")))

COMPROMISO = Entity(
    "compromiso", "commitments", owner="produccion", label="Compromiso", about="Pauta comercial contratada",
    title="client", managed=False, note="a rediseñar en A6",
    fields=(Field("client"), Field("campaign"), Field("contract_ref"), Field("asset_id", "int", ref="pieza"),
            Field("plays_required", "int"), Field("window_start", "datetime"), Field("window_end", "datetime")))
