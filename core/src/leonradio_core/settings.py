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


def load() -> dict[str, Any]:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict[str, Any]) -> None:
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(p)                       # escritura atómica: un corte de luz no deja el archivo a medias
