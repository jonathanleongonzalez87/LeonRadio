"""Rutas que llegan del navegador: solo se aceptan carpetas permitidas.

Lugares de partida: la biblioteca de la emisora, Música, Descargas y Escritorio del usuario, más las que se
agreguen con `leonradio carpetas --agregar` (solo por consola: agregarlas desde la API anularía la protección).
Nunca «Inicio» (contiene AppData) ni unidades completas.
"""

from __future__ import annotations

import ipaddress
import os
import re
from pathlib import Path
from typing import Literal

from . import settings

MSG_FUERA = "Esa carpeta no está entre las permitidas. Agrégala con `leonradio carpetas --agregar`."


def is_loopback(host: str) -> bool:
    """`127.0.0.0/8`, `::1` y `localhost`; todo lo demás (0.0.0.0, `::`, una IP de la red) es «red»."""
    host = (host or "").strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return ip.is_loopback


def host_header_is_loopback(value: str) -> bool:
    """¿La cabecera `Host` (con o sin puerto) nombra este equipo? (anti DNS-rebinding)."""
    value = (value or "").strip().lower()
    if value.startswith("["):
        name = value[1:].split("]", 1)[0]
    else:
        name = value.rsplit(":", 1)[0] if value.count(":") == 1 else value
    return name in ("localhost", "::1") or (name.count(".") == 3 and is_loopback(name) and name.startswith("127."))


def places(library_dir: str | None, home: Path | None = None) -> list[tuple[str, Path]]:
    """(nombre, carpeta resuelta) de cada lugar permitido que exista, sin repetidos."""
    home = home or Path.home()
    cands: list[tuple[str, Path]] = []
    if library_dir:
        cands.append(("Biblioteca", Path(library_dir)))
    for label, name in (("Música", "Music"), ("Descargas", "Downloads"), ("Escritorio", "Desktop")):
        cands += [(label, home / name), (label + " (OneDrive)", home / "OneDrive" / name)]   # OneDrive suele redirigir estas carpetas
    for extra in settings.get_allowed_paths():
        cands.append((Path(extra).name or str(extra), Path(extra)))
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for label, p in cands:
        try:
            r = p.resolve(strict=True)
        except OSError:
            continue
        key = os.path.normcase(str(r))
        if r.is_dir() and key not in seen:
            seen.add(key)
            out.append((label, r))
    names = {n for n, _p in out}
    return [(n[:-11] if n.endswith(" (OneDrive)") and n[:-11] not in names else n, p) for n, p in out]


def allowed_roots(library_dir: str | None, home: Path | None = None) -> list[Path]:
    return [p for _l, p in places(library_dir, home)]


_protected_dbs: set[Path] = set()


def protect(db_file: str) -> None:
    """Protege también la base elegida con `--db`/`LEONRADIO_DB` (el servidor la registra al arrancar)."""
    if db_file and db_file != ":memory:":
        _protected_dbs.add(Path(db_file))


def _forbidden() -> list[Path]:
    """Carpeta de ajustes (config.json con claves), la base y sus copias (por defecto y la elegida con --db)."""
    out = []
    dbs = {settings.db_path(), *_protected_dbs}
    for p in (settings.path().parent, *[d.parent / "copias" for d in dbs], *dbs):
        try:
            out.append(p.resolve())
        except OSError:
            pass
    return out


def _hit_forbidden(p: Path) -> bool:
    if any(p.is_relative_to(f) for f in _forbidden()):
        return True
    dbs = {settings.db_path(), *_protected_dbs}                # y los -wal/-shm junto a la base
    return any(p.parent == d.parent.resolve() and p.name.lower().startswith(d.name.lower()) for d in dbs)


def _unsafe_text(text: str) -> bool:
    """Rutas de red/dispositivo y nombres con «:» (flujos ADS), ANTES de resolver (resolver una UNC abre una conexión SMB)."""
    if not text.strip() or "\0" in text:
        return True
    norm = text.replace("/", "\\")
    drive = os.path.splitdrive(text)[0]
    if norm.startswith("\\\\") or Path(text).drive.startswith(("\\\\", "//")) or drive.startswith(("\\\\", "//")):
        return True
    if drive and not re.fullmatch(r"[A-Za-z]:", drive):
        return True
    return os.name == "nt" and ":" in text[len(drive):]


def check(path: str, roots: list[Path], *, must: Literal["dir", "file", "any"] = "any",
          create_ok: bool = False) -> Path:
    """Ruta resuelta si está dentro de `roots`; si no, `ValueError(MSG_FUERA)` (sin la ruta en el mensaje)."""
    text = str(path or "")
    if _unsafe_text(text):                       # UNC, dispositivos y «:»: antes de resolver, que ya toca la red
        raise ValueError(MSG_FUERA)
    try:
        p = Path(text).resolve(strict=not create_ok)
    except (OSError, ValueError, RuntimeError):
        raise ValueError(MSG_FUERA) from None
    resolved = []
    for r in roots:
        try:
            resolved.append(Path(r).resolve())
        except OSError:
            pass
    if not any(p.is_relative_to(r) for r in resolved) or _hit_forbidden(p):
        raise ValueError(MSG_FUERA)
    if must == "dir" and not p.is_dir():
        raise ValueError("no es una carpeta")
    if must == "file" and not p.is_file():
        raise ValueError("no es un archivo")
    return p


def validate_new_root(path: str) -> Path:
    """Para `leonradio carpetas --agregar`: debe existir, ser carpeta, no UNC, no una unidad entera ni contener los ajustes."""
    text = str(path or "")
    if _unsafe_text(text):
        raise ValueError("no se aceptan rutas de red (UNC) ni nombres con «:»")
    try:
        p = Path(text).resolve(strict=True)
    except OSError:
        raise ValueError("esa carpeta no existe") from None
    if not p.is_dir():
        raise ValueError("eso no es una carpeta")
    if p.parent == p:
        raise ValueError("no se permite una unidad completa: elige una carpeta dentro de ella")
    if any(f.is_relative_to(p) for f in _forbidden()):
        raise ValueError("esa carpeta contiene los ajustes de LeonRadio (claves y base de datos)")
    return p
