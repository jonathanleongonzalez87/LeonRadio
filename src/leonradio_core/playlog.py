"""Historial de emisión: registro, reportes y cumplimiento de compromisos."""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPORT_COLUMNS = [
    "started_at", "ended_at", "played_ms", "kind", "title", "artist",
    "isrc", "composer", "publisher", "source", "output", "status",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def record_play(
    conn: sqlite3.Connection,
    *,
    station: str,
    asset_id: int | None = None,
    started_at: str | None = None,
    ended_at: str | None = None,
    played_ms: int | None = None,
    source: str = "auto",
    output: str = "all",
    commitment_id: int | None = None,
    status: str = "completed",
    **override: str | None,
) -> int:
    """Registra algo que sonó. Copia los metadatos del asset al momento de emitir."""
    meta = {"kind": "other", "title": "(sin título)", "artist": None,
            "isrc": None, "composer": None, "publisher": None}
    if asset_id is not None:
        row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise ValueError(f"asset {asset_id} no existe")
        meta = {k: row[k] for k in meta}
    meta.update({k: v for k, v in override.items() if k in meta and v is not None})
    cur = conn.execute(
        """INSERT INTO playlog (station, started_at, ended_at, played_ms, asset_id,
               kind, title, artist, isrc, composer, publisher,
               source, output, commitment_id, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (station, started_at or now_utc(), ended_at, played_ms, asset_id,
         meta["kind"], meta["title"], meta["artist"], meta["isrc"],
         meta["composer"], meta["publisher"], source, output, commitment_id, status),
    )
    conn.commit()
    return cur.lastrowid


def export_csv(
    conn: sqlite3.Connection,
    dest: str | Path,
    start: str,
    end: str,
    kinds: tuple[str, ...] | None = None,
    only_completed: bool = True,
) -> int:
    """Exporta el historial entre [start, end) a CSV. Devuelve filas escritas.

    Uso típico: kinds=('music',) para sociedades de gestión (autores/intérpretes),
    kinds=('spot',) para constancias de pauta de anunciantes.
    """
    sql = f"SELECT {', '.join(REPORT_COLUMNS)} FROM playlog WHERE started_at >= ? AND started_at < ?"
    params: list = [start, end]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        params += list(kinds)
    if only_completed:
        sql += " AND status = 'completed'"
    sql += " ORDER BY started_at"
    rows = conn.execute(sql, params).fetchall()
    with open(dest, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(REPORT_COLUMNS)
        w.writerows([tuple(r) for r in rows])
    return len(rows)


def commitment_status(conn: sqlite3.Connection, commitment_id: int) -> dict:
    """Contratado vs emitido de un compromiso comercial."""
    c = conn.execute("SELECT * FROM commitments WHERE id = ?", (commitment_id,)).fetchone()
    if c is None:
        raise ValueError(f"compromiso {commitment_id} no existe")
    delivered = conn.execute(
        """SELECT COUNT(*) FROM playlog
           WHERE commitment_id = ? AND status = 'completed'
             AND started_at >= ? AND started_at < ?""",
        (commitment_id, c["window_start"], c["window_end"]),
    ).fetchone()[0]
    required = c["plays_required"]
    return {
        "client": c["client"], "campaign": c["campaign"],
        "required": required, "delivered": delivered,
        "missing": max(required - delivered, 0),
        "complete": delivered >= required,
    }
