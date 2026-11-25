"""Ficheros: lo que reproducen las listas (Emisión y las 4 Auxiliares).

Un *fichero* es cualquier elemento de una lista. Hay tres tipos:

* ``audio``  — un archivo de sonido de la biblioteca (música, jingle, pisador, separador, cuña…).
* ``event``  — una acción que la lista ejecuta al llegar a ella: ``pause`` (silencio N s),
               ``wait_until`` (esperar al minuto de la hora), ``command`` (ejecutar un comando de LeonRadio)
               o ``marker`` (marca visible que no hace nada, p. ej. «Inicio de tanda»).
* ``other``  — cualquier otra cosa que una lista pueda llevar (hoy: ``note``, una nota para el locutor).
               Es el punto de extensión para que los addons añadan sus propios tipos.

Todos comparten la misma forma (un dict serializable a JSON), de modo que la UI, el historial y los addons
tratan una lista de ficheros sin distinguir qué hay dentro.
"""

from __future__ import annotations

import itertools
from typing import Any

from .. import sdk

AUDIO, EVENT, OTHER = "audio", "event", "other"
FILE_TYPES = {AUDIO: "Audio", EVENT: "Evento", OTHER: "Otro"}
EVENT_TYPES = ("pause", "wait_until", "command", "marker")

_uid = itertools.count(1)


def new_uid() -> str:
    return f"f{next(_uid)}"


def audio_file(asset: dict[str, Any]) -> dict[str, Any]:
    """Fichero de audio a partir de una fila de `assets`."""
    return {
        "uid": new_uid(), "file": AUDIO, "kind": asset["kind"], "id": asset.get("id"),
        "title": asset["title"], "artist": asset.get("artist"),
        "duration_ms": int(asset.get("duration_ms") or 30000), "path": asset.get("path"),
        "intro_ms": asset.get("intro_ms"), "outro_ms": asset.get("outro_ms"), "event": None,
    }


def event_file(etype: str, title: str, **params: Any) -> dict[str, Any]:
    if etype not in EVENT_TYPES:
        raise ValueError(f"tipo de evento desconocido: {etype}")
    seconds = float(params.get("seconds", 0)) if etype == "pause" else 0.0
    return {
        "uid": new_uid(), "file": EVENT, "kind": etype, "id": None, "title": title, "artist": None,
        "duration_ms": int(seconds * 1000), "path": None, "intro_ms": None, "outro_ms": None,
        "event": {"type": etype, **params},
    }


def other_file(kind: str, title: str, **meta: Any) -> dict[str, Any]:
    return {
        "uid": new_uid(), "file": OTHER, "kind": kind, "id": None, "title": title, "artist": None,
        "duration_ms": 0, "path": None, "intro_ms": None, "outro_ms": None, "event": None, "meta": meta,
    }


def templates() -> list[dict[str, Any]]:
    """Plantillas de eventos y otros ficheros (data/event_files.json)."""
    return sdk.load_json("event_files.json")["templates"]


def from_template(key: str) -> dict[str, Any]:
    for t in templates():
        if t["key"] == key:
            if t["file"] == EVENT:
                return event_file(t["type"], t["title"], **t.get("params", {}))
            return other_file(t["type"], t["title"], **t.get("params", {}))
    raise ValueError(f"plantilla desconocida: {key}")


def copy_of(item: dict[str, Any]) -> dict[str, Any]:
    """Copia con `uid` nuevo (el mismo fichero puede estar dos veces en una lista)."""
    return {**item, "uid": new_uid()}
