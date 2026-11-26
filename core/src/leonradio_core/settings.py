"""Ajustes del usuario (fuera del repositorio): dispositivos de audio por destino y entradas de línea.

Se guardan en `%LOCALAPPDATA%\\LeonRadio\\config.json` (o `~/.config/leonradio/config.json`); la variable
`LEONRADIO_CONFIG` permite usar otro archivo (las pruebas lo usan).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def path() -> Path:
    env = os.environ.get("LEONRADIO_CONFIG")
    if env:
        return Path(env)
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) / "LeonRadio" if base else Path.home() / ".config" / "leonradio") / "config.json"


class SettingsError(RuntimeError):
    pass


def load(strict: bool = False) -> dict[str, Any]:
    """Ajustes guardados. Si no existe, `{}`. Si existe pero no se puede leer o entender: `{}`, o con
    `strict=True` (lo usan las escrituras) un `SettingsError`, para no pisar la contraseña de Icecast ni lo demás."""
    p = path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    if strict:
        raise SettingsError("No se pudo leer el archivo de ajustes (config.json): arréglalo o muévelo antes de guardar cambios.")
    return {}


def save(data: dict[str, Any]) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)                       # escritura atómica: un corte de luz no deja el archivo a medias


def db_path(explicit: str | os.PathLike | None = None) -> Path:
    """Base de datos: `--db`, `LEONRADIO_DB`, o `leonradio.db` junto al config (`LEONRADIO_CONFIG` o la carpeta del usuario)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("LEONRADIO_DB")
    if env:
        return Path(env)
    return path().parent / "leonradio.db"


def get_allowed_paths() -> list[str]:
    """Carpetas permitidas agregadas con `leonradio carpetas --agregar` (ya resueltas)."""
    raw = load().get("paths", {})
    items = raw.get("allowed", []) if isinstance(raw, dict) else []
    return [str(p) for p in items if isinstance(p, str) and p]


def set_allowed_paths(paths: list[str]) -> None:
    data = load(strict=True)
    data["paths"] = {**(data.get("paths") if isinstance(data.get("paths"), dict) else {}), "allowed": list(paths)}
    save(data)


def get_auth() -> dict[str, Any]:
    """`{"key_hash": "scrypt$…", "changed": "<ISO>"}`; vacío si aún no hay clave. La clave en claro no se guarda."""
    raw = load().get("auth", {})
    return raw if isinstance(raw, dict) else {}


def set_auth_hash(key_hash: str) -> None:
    from datetime import datetime, timezone

    data = load(strict=True)
    data["auth"] = {"key_hash": key_hash, "changed": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save(data)
