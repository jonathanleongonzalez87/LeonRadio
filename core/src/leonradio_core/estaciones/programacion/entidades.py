"""Entidades de Programación: el catálogo musical y la pieza."""

from ...entities import Entity, Field

PIEZA = Entity(
    "pieza", "assets", owner="programacion", label="Pieza", about="Archivo de audio de la biblioteca",
    title="title", managed=False, active_sql="status = 'active'",
    fields=(Field("kind"), Field("title"), Field("artist"), Field("album"), Field("year", "int"), Field("decade"),
            Field("isrc"), Field("duration_ms", "int"), Field("status"),
            Field("artista_id", "int", ref="artista"), Field("album_id", "int", ref="album"),
            Field("genero_id", "int", ref="genero")))

ARTISTA = Entity(
    "artista", "artista", owner="programacion", label="Artista", about="Quien interpreta las piezas",
    fields=(Field("nombre", required=True), Field("nombre_norm", derived_from="nombre", unique=True),
            Field("notas", max_len=2000)))

ALBUM = Entity(
    "album", "album", owner="programacion", label="Álbum", about="Disco o colección de un artista", title="titulo",
    fields=(Field("titulo", required=True), Field("titulo_norm", derived_from="titulo"),
            Field("artista_id", "int", ref="artista"), Field("anio", "int")))

GENERO = Entity(
    "genero", "genero", owner="programacion", label="Género", about="Estilo musical",
    fields=(Field("nombre", required=True), Field("nombre_norm", derived_from="nombre", unique=True)))

ALL = (PIEZA, ARTISTA, ALBUM, GENERO)
