"""Esquema SQLite de LeonRadio.

Principio del historial (playlog): cada fila es un hecho inmutable de lo que
SONÓ. Por eso copia título/artista/ISRC en vez de depender solo del asset:
si luego se edita o borra el archivo, el reporte histórico no cambia.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

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


def connect(path: str | Path = ":memory:", *, shared: bool = False) -> sqlite3.Connection:
    """`shared=True` permite usar la conexión desde varios hilos (servidor); proteger con un lock."""
    conn = sqlite3.connect(str(path), check_same_thread=not shared)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
