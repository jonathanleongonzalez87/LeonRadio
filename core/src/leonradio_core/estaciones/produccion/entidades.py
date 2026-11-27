"""Entidades de Producción: clientes, contratos (pauta o patrocinio) y compromisos de pauta."""

from ...entities import Entity, Field

CLIENTE = Entity(
    "cliente", "cliente", owner="produccion", label="Cliente", about="Anunciante o patrocinador que contrata con la emisora",
    fields=(Field("nombre", required=True), Field("nombre_norm", derived_from="nombre", unique=True),
            Field("notas", max_len=2000)))

CONTRATO = Entity(
    "contrato", "contrato", owner="produccion", label="Contrato", about="Acuerdo de pauta o patrocinio con un cliente",
    title="codigo",
    fields=(Field("codigo", required=True, unique=True, max_len=40), Field("cliente_id", "int", required=True, ref="cliente"),
            Field("tipo", required=True, choices=("pauta", "patrocinio")),
            Field("desde", "date", required=True), Field("hasta", "date", required=True),
            Field("valor_cop", "int"), Field("descripcion", max_len=2000)))

COMPROMISO = Entity(                                   # tabla de v1: conserva sus nombres de columna (playlog.commitment_id la apunta)
    "compromiso", "commitments", owner="produccion", label="Compromiso",
    about="Cuñas contratadas: cuántas, de qué pieza, en qué vigencia y franja", title="window_start",
    fields=(Field("contrato_id", "int", required=True, ref="contrato"), Field("asset_id", "int", ref="pieza"),
            Field("campaign"), Field("plays_required", "int", required=True),
            Field("window_start", "datetime", required=True), Field("window_end", "datetime", required=True),
            Field("daypart_start", max_len=5), Field("daypart_end", max_len=5), Field("notes", max_len=2000),
            Field("client"), Field("contract_ref")))  # heredadas de v1: solo lectura para filas antiguas

ALL = (CLIENTE, CONTRATO, COMPROMISO)
