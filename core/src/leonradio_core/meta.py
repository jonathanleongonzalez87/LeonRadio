"""Metadatos y carátula de un archivo de audio, leídos con mutagen (tolerante a archivos sin etiquetas)."""

from __future__ import annotations

from pathlib import Path

FIELDS = ("artist", "title", "album", "year", "genre", "comment")


def _first(tags, key) -> str:
    try:
        v = tags.get(key)
        return str(v[0]).strip() if v else ""
    except Exception:  # noqa: BLE001
        return ""


def read_tags(path: str | Path) -> dict:
    out = {k: "" for k in FIELDS}
    try:
        import mutagen

        easy = mutagen.File(path, easy=True)
        if easy is not None and easy.tags:
            out["artist"], out["title"] = _first(easy.tags, "artist"), _first(easy.tags, "title")
            out["album"], out["genre"] = _first(easy.tags, "album"), _first(easy.tags, "genre")
            out["year"] = _first(easy.tags, "date")[:4]
        raw = mutagen.File(path)
        tags = getattr(raw, "tags", None)
        if tags is not None:
            if hasattr(tags, "getall"):                                   # ID3
                comm = tags.getall("COMM")
                out["comment"] = str(comm[0].text[0]).strip() if comm and comm[0].text else ""
            else:                                                         # MP4 / Vorbis
                out["comment"] = _first(tags, "\xa9cmt") or _first(tags, "comment")
    except Exception:  # noqa: BLE001
        pass
    return out


def read_cover(path: str | Path) -> tuple[bytes, str] | None:
    """Carátula incrustada (bytes, tipo MIME) o None."""
    try:
        import mutagen

        f = mutagen.File(path)
        if f is None:
            return None
        pics = getattr(f, "pictures", None)                               # FLAC
        if pics:
            return bytes(pics[0].data), pics[0].mime or "image/jpeg"
        tags = getattr(f, "tags", None)
        if tags is None:
            return None
        if hasattr(tags, "getall"):                                       # ID3
            apic = tags.getall("APIC")
            if apic:
                return bytes(apic[0].data), apic[0].mime or "image/jpeg"
        covr = tags.get("covr") if hasattr(tags, "get") else None         # MP4
        if covr:
            return bytes(covr[0]), "image/png" if getattr(covr[0], "imageformat", 13) == 14 else "image/jpeg"
    except Exception:  # noqa: BLE001
        pass
    return None
