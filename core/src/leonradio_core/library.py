"""Escáner de biblioteca: lee una carpeta de emisora y llena `assets`.

Convención de carpetas (la de Rockland Radio):
    Música/<década>/…                 -> music
    Vestido General/Jingles/…         -> jingle
    Vestido General/Pisadores/…       -> pisador
    Vestido General/Separadores/…     -> separador
Detecta duplicados por hash de contenido (p. ej. «Copia de …»).
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import stat
from pathlib import Path

log = logging.getLogger("leonradio.library")
AUDIO_EXT = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
_FOLDER_KIND = {"jingles": "jingle", "pisadores": "pisador", "separadores": "separador",
                "spots": "spot", "música": "music", "musica": "music"}
_DECADE = re.compile(r"^(\d{2})s$", re.I)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def classify(rel_parts: tuple[str, ...]) -> tuple[str, str | None]:
    kind, decade = "other", None
    for part in rel_parts[:-1]:
        low = part.lower()
        if low in _FOLDER_KIND:
            kind = _FOLDER_KIND[low]
        if _DECADE.match(low):
            decade = low
    return kind, decade


def _tags(path: Path) -> dict:
    """Metadatos vía mutagen; tolerante a archivos sin etiquetas."""
    out: dict = {"duration_ms": None, "title": None, "artist": None, "album": None}
    try:
        import mutagen
        f = mutagen.File(path, easy=True)
        if f is not None:
            if f.info is not None and getattr(f.info, "length", None):
                out["duration_ms"] = int(f.info.length * 1000)
            for key in ("title", "artist", "album"):
                if f.tags and f.tags.get(key):
                    out[key] = str(f.tags[key][0])
    except Exception:
        pass
    return out


def title_artist_from_name(stem: str) -> tuple[str, str | None]:
    """«Título - Artista» (convención de los archivos de Rockland)."""
    stem = re.sub(r"^Copia de\s+", "", stem)
    if " - " in stem:
        title, artist = stem.rsplit(" - ", 1)
        return title.strip(), artist.strip()
    return stem.strip(), None


def scan(conn: sqlite3.Connection, root: str | Path, *, lock=None, progress=None, cancel=None) -> dict:
    """Escaneo incremental: solo lee lo nuevo o cambiado (tamaño/mtime); lo que desapareció pasa a `retired`, nunca se borra."""
    import contextlib
    import os

    root = Path(root)
    out = {"added": 0, "duplicates": 0, "updated": 0, "retired": 0, "reactivated": 0, "unchanged": 0, "cancelled": False}
    if not root.is_dir():
        log.warning("La carpeta de la biblioteca no existe o no está disponible: %s (no se retira nada)", root)
        return out
    files = []
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in AUDIO_EXT:
            try:
                st = p.stat()                      # un solo stat por archivo
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                files.append((p, st))
    seen: set[str] = set()
    for i, (p, st) in enumerate(files, 1):
        if cancel and cancel():
            out["cancelled"] = True
            break
        key = str(p)
        seen.add(key)
        with lock or contextlib.nullcontext():
            row = conn.execute("SELECT id, status, size_bytes, mtime_ns FROM assets WHERE path = ?", (key,)).fetchone()
        if row and row["size_bytes"] is None:      # fila previa a la migración 2: solo se anotan tamaño y fecha
            with lock or contextlib.nullcontext():
                conn.execute("UPDATE assets SET size_bytes = ?, mtime_ns = ? WHERE id = ?", (st.st_size, st.st_mtime_ns, row["id"]))
        if row and row["size_bytes"] in (None, st.st_size) and row["mtime_ns"] in (None, st.st_mtime_ns):
            out["unchanged"] += 1
            if row["status"] == "retired":
                with lock or contextlib.nullcontext():
                    conn.execute("UPDATE assets SET status = 'active' WHERE id = ?", (row["id"],))
                out["reactivated"] += 1
        else:
            kind, decade = classify(p.relative_to(root).parts)
            digest = sha256_of(p)
            tags = _tags(p)
            name_title, name_artist = (title_artist_from_name(p.stem) if kind == "music"
                                       else (re.sub(r"^Copia de\s+", "", p.stem).strip(), None))
            title, artist = tags["title"] or name_title, tags["artist"] or name_artist
            with lock or contextlib.nullcontext():
                if row:
                    conn.execute(
                        """UPDATE assets SET sha256 = ?, kind = ?, title = ?, artist = ?, album = ?, decade = ?,
                                  duration_ms = ?, size_bytes = ?, mtime_ns = ?,
                                  status = CASE WHEN status = 'retired' THEN 'active' ELSE status END WHERE id = ?""",
                        (digest, kind, title, artist, tags["album"], decade, tags["duration_ms"],
                         st.st_size, st.st_mtime_ns, row["id"]))
                    out["updated"] += 1
                else:
                    original = conn.execute(
                        "SELECT id FROM assets WHERE sha256 = ? AND status = 'active'", (digest,)).fetchone()
                    conn.execute(
                        """INSERT INTO assets (path, sha256, kind, title, artist, album, decade,
                                               duration_ms, status, duplicate_of, size_bytes, mtime_ns)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (key, digest, kind, title, artist, tags["album"], decade, tags["duration_ms"],
                         "duplicate" if original else "active", original["id"] if original else None,
                         st.st_size, st.st_mtime_ns))
                    out["duplicates"] += bool(original)
                    out["added"] += 1
        if i % 200 == 0:
            with lock or contextlib.nullcontext():
                conn.commit()
        if progress:
            progress(i, len(files))
    with lock or contextlib.nullcontext():
        conn.commit()
        if not out["cancelled"]:
            prefix = str(root).rstrip("\\/") + os.sep
            rows = conn.execute("SELECT id, path FROM assets WHERE status IN ('active','duplicate') AND substr(path, 1, ?) = ?",
                                (len(prefix), prefix)).fetchall()
            if not seen and rows:
                log.warning("No se encontró ningún audio en %s pero la base tenía %d: no se retira nada (¿disco desconectado?)",
                            root, len(rows))
            else:
                gone = [(r["id"],) for r in rows if r["path"] not in seen]
                conn.executemany("UPDATE assets SET status = 'retired' WHERE id = ?", gone)
                out["retired"] = len(gone)
                conn.commit()
    return out


def add_file(conn: sqlite3.Connection, path: str | Path, lock=None, kind: str = "music") -> int:
    """Agrega un archivo suelto (de cualquier carpeta) a la biblioteca y devuelve su id. Si ya estaba, devuelve el existente."""
    import contextlib

    p = Path(path)
    if p.suffix.lower() not in AUDIO_EXT or not p.is_file():
        raise ValueError("no es un archivo de audio compatible")
    with lock or contextlib.nullcontext():
        row = conn.execute("SELECT id FROM assets WHERE path = ? AND status = 'active'", (str(p),)).fetchone()
        if row:
            return row["id"]
    digest = sha256_of(p)
    tags = _tags(p)
    name_title, name_artist = title_artist_from_name(p.stem)
    with lock or contextlib.nullcontext():
        row = conn.execute("SELECT id FROM assets WHERE sha256 = ? AND status = 'active'", (digest,)).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            """INSERT INTO assets (path, sha256, kind, title, artist, album, decade, duration_ms, status)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (str(p), digest, kind, tags["title"] or name_title, tags["artist"] or name_artist, tags["album"],
             None, tags["duration_ms"], "active"))
        conn.commit()
        return int(cur.lastrowid)


def import_m3u(conn: sqlite3.Connection, m3u: str | Path) -> list[int]:
    """Importa un .m3u cuyas rutas vienen de OTRA máquina: resuelve por nombre de archivo."""
    ids: list[int] = []
    for line in Path(m3u).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[\\/]", line)[-1]
        row = conn.execute(
            "SELECT id FROM assets WHERE path LIKE ? AND status = 'active' LIMIT 1",
            (f"%{name}",),
        ).fetchone()
        if row:
            ids.append(row["id"])
    return ids
