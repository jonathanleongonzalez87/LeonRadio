"""Copias de seguridad automáticas de la base: una al arrancar, en `copias/` junto a la base, las 7 más recientes."""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import db

log = logging.getLogger("leonradio.backup")
_STAMP = "%Y%m%d-%H%M%S"


def make_backup(db_path: str | Path, keep: int = 7, min_interval_s: int = 3600, *,
                force: bool = False, now: datetime | None = None) -> Path | None:
    """Copia consistente de la base (API de backup de SQLite). Devuelve la ruta o None si no copió. Nunca lanza."""
    try:
        return _make_backup(Path(db_path), keep, min_interval_s, force, now or datetime.now(timezone.utc))
    except Exception as exc:                      # disco lleno, permisos…: no impide arrancar
        log.warning("No se pudo hacer la copia de seguridad de la base: %s", exc)
        return None


def _make_backup(src_path: Path, keep: int, min_interval_s: int, force: bool, now: datetime) -> Path | None:
    if str(src_path) == ":memory:" or not src_path.is_file() or src_path.stat().st_size == 0:
        return None
    folder = src_path.parent / "copias"
    folder.mkdir(exist_ok=True)
    existing = sorted(p for p in folder.glob("leonradio-*.db") if p.is_file())
    src = sqlite3.connect(str(src_path))
    try:
        if db.version(src) < len(db.MIGRATIONS):   # migración pendiente: siempre hay copia previa
            force = True
        if existing and not force:
            try:
                last = datetime.strptime(existing[-1].stem.removeprefix("leonradio-")[:15], _STAMP).replace(tzinfo=timezone.utc)
                if (now - last).total_seconds() < min_interval_s:
                    return None
            except ValueError:
                pass
        final = folder / f"leonradio-{now.astimezone(timezone.utc).strftime(_STAMP)}.db"
        n = 1
        while final.exists():                      # misma resolución de 1 s: nombre único, sin pisar la anterior
            final = folder / f"leonradio-{now.astimezone(timezone.utc).strftime(_STAMP)}_{n}.db"
            n += 1
        tmp = final.with_name(final.name + ".tmp")
        dst = sqlite3.connect(str(tmp))
        try:
            src.backup(dst)
        except BaseException:
            dst.close()
            tmp.unlink(missing_ok=True)
            raise
        try:
            ok = dst.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        finally:
            dst.close()
        if not ok:                                 # copia dañada: no se rota (las anteriores siguen siendo la red de seguridad)
            tmp.unlink(missing_ok=True)
            log.warning("La base de datos no pasó la verificación de integridad: no se rotan las copias anteriores.")
            return None
        os.replace(tmp, final)
    finally:
        src.close()
    for old in sorted(p for p in folder.glob("leonradio-*.db") if p.is_file())[:-keep]:
        old.unlink(missing_ok=True)
    return final
