"""Esquema SQLite de LeonRadio.

Principio del historial (playlog): cada fila es un hecho inmutable de lo que
SONÓ. Por eso copia título/artista/ISRC en vez de depender solo del asset:
si luego se edita o borra el archivo, el reporte histórico no cambia.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS assets (
    id            INTEGER PRIMARY KEY,
    path          TEXT NOT NULL UNIQUE,
    sha256        TEXT,
    kind          TEXT NOT NULL CHECK (kind IN
                  ('music','jingle','pisador','separador','spot','voice','effect','other')),
    title         TEXT NOT NULL,
    artist        TEXT,
    album         TEXT,
    year          INTEGER,
    decade        TEXT,
    isrc          TEXT,
    composer      TEXT,
    publisher     TEXT,
    duration_ms   INTEGER,
    intro_ms      INTEGER,
    outro_ms      INTEGER,
    loudness_lufs REAL,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','duplicate','retired')),
    duplicate_of  INTEGER REFERENCES assets(id),
    added_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);
CREATE INDEX IF NOT EXISTS idx_assets_kind ON assets(kind);
CREATE INDEX IF NOT EXISTS idx_assets_sha ON assets(sha256);

-- Compromisos comerciales: pauta contratada que la emisora debe cumplir.
CREATE TABLE IF NOT EXISTS commitments (
    id             INTEGER PRIMARY KEY,
    client         TEXT NOT NULL,
    campaign       TEXT,
    contract_ref   TEXT,
    asset_id       INTEGER REFERENCES assets(id),
    plays_required INTEGER NOT NULL,
    window_start   TEXT NOT NULL,   -- ISO 8601 UTC
    window_end     TEXT NOT NULL,
    daypart_start  TEXT,            -- HH:MM hora local de la emisora (opcional)
    daypart_end    TEXT,
    notes          TEXT
);

-- Historial inmutable de emisión (as-run log).
CREATE TABLE IF NOT EXISTS playlog (
    id            INTEGER PRIMARY KEY,
    station       TEXT NOT NULL,
    started_at    TEXT NOT NULL,    -- ISO 8601 UTC
    ended_at      TEXT,
    played_ms     INTEGER,
    asset_id      INTEGER REFERENCES assets(id) ON DELETE SET NULL,
    kind          TEXT NOT NULL,
    file_type     TEXT NOT NULL DEFAULT 'audio' CHECK (file_type IN ('audio','event','other')),
    title         TEXT NOT NULL,
    artist        TEXT,
    isrc          TEXT,
    composer      TEXT,
    publisher     TEXT,
    source        TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto','live','cart','manual')),
    output        TEXT NOT NULL DEFAULT 'all'  CHECK (output IN ('fm','stream','all')),
    commitment_id INTEGER REFERENCES commitments(id) ON DELETE SET NULL,
    status        TEXT NOT NULL DEFAULT 'completed'
                  CHECK (status IN ('completed','skipped','interrupted','failed'))
);
CREATE INDEX IF NOT EXISTS idx_playlog_started ON playlog(started_at);
CREATE INDEX IF NOT EXISTS idx_playlog_commit ON playlog(commitment_id);
"""


def _m1_esquema_inicial(conn: sqlite3.Connection) -> None:
    # executescript haría COMMIT implícito: se corre sentencia por sentencia dentro de la transacción
    for stmt in SCHEMA_V1.split(";"):
        if stmt.strip():
            conn.execute(stmt)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(playlog)")}
    if "file_type" not in cols:          # base creada antes de existir el tipo de fichero
        conn.execute("ALTER TABLE playlog ADD COLUMN file_type TEXT NOT NULL DEFAULT 'audio'")


def _m2_escaneo_incremental(conn: sqlite3.Connection) -> None:
    conn.execute("ALTER TABLE assets ADD COLUMN size_bytes INTEGER")
    conn.execute("ALTER TABLE assets ADD COLUMN mtime_ns INTEGER")


# El índice + 1 es la versión (PRAGMA user_version). Nunca se edita una migración publicada: se agrega otra al final.
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_m1_esquema_inicial, _m2_escaneo_incremental]


def version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def check_version(conn: sqlite3.Connection) -> None:
    if version(conn) > len(MIGRATIONS):
        raise RuntimeError("La base de datos fue creada por una versión más nueva de LeonRadio. "
                           "Actualiza LeonRadio o usa otra base con --db.")


def migrate(conn: sqlite3.Connection) -> None:
    check_version(conn)
    for n in range(version(conn) + 1, len(MIGRATIONS) + 1):
        conn.execute("BEGIN IMMEDIATE")
        try:
            MIGRATIONS[n - 1](conn)
            conn.execute(f"PRAGMA user_version = {n}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise


def connect(path: str | Path = ":memory:", *, shared: bool = False) -> sqlite3.Connection:
    """`shared=True` permite usar la conexión desde varios hilos (servidor); proteger con un lock."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=not shared)
    try:
        conn.row_factory = sqlite3.Row
        check_version(conn)                       # antes de cualquier PRAGMA que escriba: una base futura no se toca
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")  # en :memory: devuelve «memory» y se ignora
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        migrate(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def close(conn: sqlite3.Connection) -> None:
    """Checkpoint del WAL y cierre: deja un único archivo .db coherente."""
    try:
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


# Migraciones de las estaciones (SQL literal, sin dependencias). Import al final: `estaciones` importa `sdk`, que importa `db`.
from .estaciones.programacion import migraciones as _programacion  # noqa: E402

MIGRATIONS.append(_programacion.m3_catalogo_musical)
