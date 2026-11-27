"""Migraciones de Producción. SQL literal: una migración publicada no cambia nunca (solo `sqlite3` y `datetime`)."""

import sqlite3
from datetime import datetime, timezone


def m4_comercial(conn: sqlite3.Connection) -> None:
    """Cliente y Contrato nuevos; `commitments` (de v1) pasa a ser entidad gestionada. Solo agrega: `playlog` no se toca."""
    std = """archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL"""
    conn.execute(f"""CREATE TABLE IF NOT EXISTS cliente (id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL, nombre_norm TEXT NOT NULL UNIQUE, notas TEXT, {std})""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS contrato (id INTEGER PRIMARY KEY,
        codigo TEXT NOT NULL UNIQUE, cliente_id INTEGER NOT NULL REFERENCES cliente(id),
        tipo TEXT NOT NULL CHECK (tipo IN ('pauta','patrocinio')), desde TEXT NOT NULL, hasta TEXT NOT NULL,
        valor_cop INTEGER CHECK (valor_cop IS NULL OR valor_cop >= 0), descripcion TEXT, {std})""")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(commitments)")}
    for name, ddl in (("contrato_id", "INTEGER REFERENCES contrato(id)"),
                      ("archived", "INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1))"),
                      ("created_at", "TEXT NOT NULL DEFAULT ''"), ("updated_at", "TEXT NOT NULL DEFAULT ''"),
                      ("created_by", "TEXT NOT NULL DEFAULT ''"), ("updated_by", "TEXT NOT NULL DEFAULT ''")):
        if name not in cols:
            conn.execute(f"ALTER TABLE commitments ADD COLUMN {name} {ddl}")
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
    conn.execute("UPDATE commitments SET created_at = ?, updated_at = ?, created_by = 'sistema', updated_by = 'sistema' "
                 "WHERE created_at = ''", (now, now))
    conn.execute("CREATE INDEX IF NOT EXISTS idx_cliente_nombre ON cliente(nombre, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_cliente ON contrato(cliente_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contrato_desde ON contrato(desde)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commitments_contrato ON commitments(contrato_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_commitments_inicio ON commitments(window_start, id)")
