"""Migraciones de Programación. SQL literal: una migración publicada no cambia nunca (solo `sqlite3` y `unicodedata`)."""

import sqlite3
import unicodedata
from collections import Counter
from datetime import datetime, timezone


def _norm(text: str) -> str:          # copia congelada de entities.norm: la migración no depende del marco
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _clean(value) -> str:
    return (value or "").strip()[:200]


def _best(counter: Counter) -> str:
    return sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def m3_catalogo_musical(conn: sqlite3.Connection) -> None:
    std = """archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL"""
    conn.execute(f"""CREATE TABLE IF NOT EXISTS genero (id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL, nombre_norm TEXT NOT NULL UNIQUE, {std})""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS artista (id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL, nombre_norm TEXT NOT NULL UNIQUE, notas TEXT, {std})""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS album (id INTEGER PRIMARY KEY,
        titulo TEXT NOT NULL, titulo_norm TEXT NOT NULL, artista_id INTEGER REFERENCES artista(id),
        anio INTEGER, {std})""")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_album_artista_titulo ON album(COALESCE(artista_id, 0), titulo_norm)")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(assets)")}
    if "artista_id" not in cols:
        conn.execute("ALTER TABLE assets ADD COLUMN artista_id INTEGER REFERENCES artista(id)")
    if "album_id" not in cols:
        conn.execute("ALTER TABLE assets ADD COLUMN album_id INTEGER REFERENCES album(id)")
    if "genero_id" not in cols:
        conn.execute("ALTER TABLE assets ADD COLUMN genero_id INTEGER REFERENCES genero(id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_artista ON assets(artista_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_album ON assets(album_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_genero ON assets(genero_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_title ON assets(title, id)")      # listado paginado de piezas
    conn.execute("CREATE INDEX IF NOT EXISTS idx_album_artista ON album(artista_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_album_titulo ON album(titulo, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artista_nombre ON artista(nombre, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_genero_nombre ON genero(nombre, id)")

    # Relleno en Python (el lower() de SQLite no une «Beyoncé»/«BEYONCÉ»). Los textos de assets no se tocan.
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    rows = conn.execute("SELECT id, artist, album FROM assets").fetchall()
    names: dict[str, Counter] = {}
    for r in rows:
        a = _clean(r["artist"])
        if a:
            names.setdefault(_norm(a), Counter())[a] += 1
    for key, counter in names.items():
        conn.execute("INSERT OR IGNORE INTO artista (nombre, nombre_norm, created_at, updated_at, created_by, updated_by) "
                     "VALUES (?,?,?,?,'sistema','sistema')", (_best(counter), key, now, now))
    artist_id = {r["nombre_norm"]: r["id"] for r in conn.execute("SELECT id, nombre_norm FROM artista")}
    link_a: list[tuple] = []
    albums: dict[tuple, Counter] = {}
    per_row: list[tuple] = []
    for r in rows:
        a, b = _clean(r["artist"]), _clean(r["album"])
        aid = artist_id.get(_norm(a)) if a else None
        if aid:
            link_a.append((aid, r["id"]))
        if b:
            albums.setdefault((aid, _norm(b)), Counter())[b] += 1
            per_row.append((r["id"], aid, _norm(b)))
    conn.executemany("UPDATE assets SET artista_id = ? WHERE id = ? AND artista_id IS NULL", link_a)
    for (aid, key), counter in albums.items():
        conn.execute("INSERT OR IGNORE INTO album (titulo, titulo_norm, artista_id, created_at, updated_at, created_by, updated_by) "
                     "VALUES (?,?,?,?,?,'sistema','sistema')", (_best(counter), key, aid, now, now))
    album_id = {(r["a"], r["titulo_norm"]): r["id"]
                for r in conn.execute("SELECT id, COALESCE(artista_id, 0) AS a, titulo_norm FROM album")}
    conn.executemany("UPDATE assets SET album_id = ? WHERE id = ? AND album_id IS NULL",
                     [(album_id[(aid or 0, key)], rid) for rid, aid, key in per_row])
