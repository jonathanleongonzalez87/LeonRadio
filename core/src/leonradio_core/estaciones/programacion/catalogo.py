"""Vincula las piezas con su artista y álbum (entidades). Se llama al arrancar y con `catalogo.sincronizar`."""

from __future__ import annotations

from ... import sdk
from ...entities import norm


def _text(value) -> str:
    return (value or "").strip()[:200]


BATCH = 500


def sync(host: sdk.Host, batch: int = BATCH) -> dict:
    """Piezas con artista/álbum de texto y sin vínculo: lo busca por `*_norm` o lo crea, y vincula. Estable = no escribe.
    Va por lotes (una transacción por lote): entre lotes se suelta `db_lock` para no frenar el audio ni la API.
    Excepción documentada a «solo por el writer»: el vínculo `assets.*_id` lo escribe Programación (dueña de `assets`)."""
    db, reg = host.db, host.entities
    w = reg.writer("programacion")
    out = {"artistas": 0, "albumes": 0, "piezas": 0}
    artistas: dict[str, int] = {}
    albumes: dict[tuple[int, str], int] = {}
    last = 0
    while True:
        with host.db_lock:
            rows = db.execute(
                "SELECT id, artist, album, artista_id, album_id FROM assets WHERE id > ? AND "
                "((artista_id IS NULL AND artist IS NOT NULL AND trim(artist) <> '') OR "
                "(album_id IS NULL AND album IS NOT NULL AND trim(album) <> '')) ORDER BY id LIMIT ?",
                (last, batch)).fetchall()
        if not rows:
            return out
        last = rows[-1]["id"]
        with reg.transaction():
            for r in rows:
                aid = r["artista_id"]
                name = _text(r["artist"])
                if aid is None and name:
                    key = norm(name)
                    if key not in artistas:
                        row = db.execute("SELECT id FROM artista WHERE nombre_norm = ?", (key,)).fetchone()
                        if row is None:
                            out["artistas"] += 1
                        artistas[key] = row["id"] if row else w.create("artista", {"nombre": name}, who="sistema")
                    aid = artistas[key]
                bid = r["album_id"]
                title = _text(r["album"])
                if bid is None and title:
                    akey = (aid or 0, norm(title))
                    if akey not in albumes:
                        row = db.execute("SELECT id FROM album WHERE COALESCE(artista_id, 0) = ? AND titulo_norm = ?",
                                         akey).fetchone()
                        if row is None:
                            out["albumes"] += 1
                        albumes[akey] = row["id"] if row else w.create("album", {"titulo": title, "artista_id": aid},
                                                                      who="sistema")
                    bid = albumes[akey]
                if (aid, bid) != (r["artista_id"], r["album_id"]):
                    db.execute("UPDATE assets SET artista_id = ?, album_id = ? WHERE id = ?", (aid, bid, r["id"]))
                    out["piezas"] += 1


def register(host: sdk.Host) -> None:
    host.register_command("catalogo.sincronizar", lambda ctx: sync(host), risk="datos")
