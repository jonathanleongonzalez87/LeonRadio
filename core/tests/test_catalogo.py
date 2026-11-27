"""S8a: migración 3 (catálogo musical), sincronización con el escaneo. Bases temporales, datos inventados."""

import sqlite3
import time
import wave

import numpy as np
import pytest

from leonradio_core import backup, db, entities, estaciones, library, sdk
from leonradio_core.estaciones.programacion import catalogo, entidades

PIEZAS = [  # (id, artist, album)
    (1, "Artista Uno", "Disco A"), (2, "artista uno ", "Disco A"), (3, "ARTISTA UNO", None),
    (4, "Beyoncé", None), (5, "BEYONCÉ", None), (6, None, "Solo Álbum"), (7, "", None),
]


def wav(path, seconds=0.2, rate=8000, freq=330):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.4 * 32767 * np.sin(2 * np.pi * freq * t)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())


def base_v2(path):
    """Base en la versión 2 con piezas sintéticas, creada con las migraciones 1 y 2 reales."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for fn in db.MIGRATIONS[:2]:
        fn(conn)
    conn.execute("PRAGMA user_version = 2")
    for pid, artist, album in PIEZAS:
        conn.execute("INSERT INTO assets (id, path, kind, title, artist, album) VALUES (?,?,'music',?,?,?)",
                     (pid, f"x{pid}.wav", f"Tema {pid}", artist, album))
    conn.commit()
    return conn


def test_migracion3_desde_v2(tmp_path):
    base_v2(tmp_path / "v2.db").close()
    antes = sqlite3.connect(str(tmp_path / "v2.db")).execute("SELECT id, artist, album FROM assets ORDER BY id").fetchall()
    conn = db.connect(tmp_path / "v2.db")
    assert db.version(conn) == len(db.MIGRATIONS) >= 3
    assert [tuple(r) for r in conn.execute("SELECT id, artist, album FROM assets ORDER BY id")] == [tuple(r) for r in antes]
    artistas = [r["nombre_norm"] for r in conn.execute("SELECT nombre_norm FROM artista ORDER BY id")]
    assert sorted(artistas) == ["artista uno", "beyoncé"]
    nombre = conn.execute("SELECT nombre FROM artista WHERE nombre_norm = 'artista uno'").fetchone()[0]
    assert nombre in ("Artista Uno", "ARTISTA UNO", "artista uno")        # el más frecuente, con desempate fijo
    link = {r["id"]: r["artista_id"] for r in conn.execute("SELECT id, artista_id FROM assets")}
    assert link[1] == link[2] == link[3] and link[4] == link[5] and link[1] != link[4]
    assert link[6] is None and link[7] is None
    albumes = conn.execute("SELECT titulo, artista_id FROM album ORDER BY id").fetchall()
    assert [a["titulo"] for a in albumes] == ["Disco A", "Solo Álbum"] and albumes[1]["artista_id"] is None
    al = {r["id"]: r["album_id"] for r in conn.execute("SELECT id, album_id FROM assets")}
    assert al[1] == al[2] and al[1] is not None and al[6] is not None and al[3] is None
    assert conn.execute("SELECT COUNT(*) FROM assets WHERE genero_id IS NOT NULL").fetchone()[0] == 0
    assert conn.execute("SELECT created_by FROM artista LIMIT 1").fetchone()[0] == "sistema"
    db.close(conn)


def test_migracion3_idempotente(tmp_path):
    conn = db.connect(tmp_path / "v.db")
    for pid, artist, album in PIEZAS:
        conn.execute("INSERT INTO assets (id, path, kind, title, artist, album) VALUES (?,?,'music',?,?,?)",
                     (pid, f"x{pid}.wav", f"Tema {pid}", artist, album))
    conn.commit()
    db.MIGRATIONS[2](conn)
    n = [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("artista", "album")]
    db.MIGRATIONS[2](conn)
    assert n == [conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("artista", "album")] == [2, 2]
    db.close(conn)


def test_migracion3_falla_revierte(tmp_path, monkeypatch):
    base_v2(tmp_path / "v2.db").close()

    original = list(db.MIGRATIONS)

    def rota(conn):
        original[2](conn)
        raise ValueError("falla al final")
    monkeypatch.setattr(db, "MIGRATIONS", [*original[:2], rota])
    with pytest.raises(ValueError):
        db.connect(tmp_path / "v2.db")
    c = sqlite3.connect(str(tmp_path / "v2.db"))
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    assert c.execute("SELECT COUNT(*) FROM sqlite_master WHERE name IN ('artista','album','genero')").fetchone()[0] == 0
    assert "artista_id" not in {r[1] for r in c.execute("PRAGMA table_info(assets)")}
    c.close()


def test_copia_previa_a_migrar(tmp_path):
    base_v2(tmp_path / "v2.db").close()
    out = backup.make_backup(tmp_path / "v2.db")
    assert out is not None and out.parent == tmp_path / "copias"
    c = sqlite3.connect(str(out))
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2 and c.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 7
    c.close()


def host_con_piezas():
    host = sdk.Host(":memory:")
    estaciones.register_all(host)
    for pid, artist, album in PIEZAS:
        host.db.execute("INSERT INTO assets (id, path, kind, title, artist, album) VALUES (?,?,'music',?,?,?)",
                        (pid, f"x{pid}.wav", f"Tema {pid}", artist, album))
    host.db.commit()
    return host


def test_sync_vincula_y_es_idempotente():
    host = host_con_piezas()
    r = catalogo.sync(host)
    assert r["artistas"] == 2 and r["albumes"] == 2 and r["piezas"] == 6
    assert host.db.execute("SELECT COUNT(*) FROM assets WHERE artist IS NOT NULL AND trim(artist) <> '' "
                           "AND artista_id IS NULL").fetchone()[0] == 0
    antes = host.db.total_changes
    assert catalogo.sync(host) == {"artistas": 0, "albumes": 0, "piezas": 0}
    assert host.db.total_changes == antes                       # la segunda pasada no escribe nada
    assert host.db.execute("SELECT created_by FROM artista LIMIT 1").fetchone()[0] == "sistema"


def test_escaneo_no_cambia_ids_y_relinkea_etiqueta_cambiada(tmp_path):
    root = tmp_path / "Radio"
    wav(root / "Música" / "20s" / "Tema A - Artista Uno.wav", freq=300)
    wav(root / "Música" / "20s" / "Tema B - Artista Uno.wav", freq=400)
    host = sdk.Host(":memory:")
    estaciones.register_all(host)
    library.scan(host.db, root, lock=host.db_lock)
    catalogo.sync(host)
    ids = host.db.execute("SELECT id, path, artist FROM assets ORDER BY id").fetchall()
    n_art = host.db.execute("SELECT COUNT(*) FROM artista").fetchone()[0]
    assert n_art == 1 and all(r["artist"] == "Artista Uno" for r in ids)
    again = library.scan(host.db, root, lock=host.db_lock)
    assert again["unchanged"] == 2 and again["updated"] == 0 and again["added"] == 0
    antes = host.db.total_changes
    catalogo.sync(host)
    assert host.db.total_changes == antes
    assert host.db.execute("SELECT id, path, artist FROM assets ORDER BY id").fetchall() == ids
    # una pieza cambia de etiqueta: pasa a «Artista Dos» y luego el archivo vuelve a decir «Artista Uno»
    host.db.execute("UPDATE assets SET artist = 'Artista Dos', artista_id = NULL WHERE id = ?", (ids[0]["id"],))
    host.db.commit()
    catalogo.sync(host)
    dos = host.db.execute("SELECT id FROM artista WHERE nombre = 'Artista Dos'").fetchone()[0]
    assert host.db.execute("SELECT artista_id FROM assets WHERE id = ?", (ids[0]["id"],)).fetchone()[0] == dos
    wav(root / "Música" / "20s" / "Tema A - Artista Uno.wav", seconds=0.4, freq=300)       # cambia tamaño y fecha
    library.scan(host.db, root, lock=host.db_lock)
    assert host.db.execute("SELECT artista_id FROM assets WHERE id = ?", (ids[0]["id"],)).fetchone()[0] is None
    catalogo.sync(host)
    uno = host.db.execute("SELECT id FROM artista WHERE nombre = 'Artista Uno'").fetchone()[0]
    assert host.db.execute("SELECT artista_id FROM assets WHERE id = ?", (ids[0]["id"],)).fetchone()[0] == uno
    assert host.db.execute("SELECT COUNT(*) FROM artista").fetchone()[0] == 2        # «Artista Dos» sigue existiendo


def test_sync_10000_piezas_ya_vinculadas():
    host = sdk.Host(":memory:")
    estaciones.register_all(host)
    host.entities.writer("programacion").create("artista", {"nombre": "Artista Uno"}, who="local")
    host.db.executemany("INSERT INTO assets (path, kind, title, artist, artista_id) VALUES (?,'music',?,'Artista Uno',1)",
                        [(f"p{i}.wav", f"Tema {i}") for i in range(10000)])
    host.db.commit()
    t0 = time.perf_counter()
    assert catalogo.sync(host)["piezas"] == 0
    assert time.perf_counter() - t0 < 0.05


def test_check_declaration_catalogo():
    host = sdk.Host(":memory:")
    for e in entidades.ALL:
        assert entities.check_declaration(host.db, e) == [], e.name


def test_sync_por_lotes_suelta_el_lock_y_da_lo_mismo():
    import threading

    def poblar():
        h = sdk.Host(":memory:")
        estaciones.register_all(h)
        h.db.executemany("INSERT INTO assets (path, kind, title, artist, album) VALUES (?,'music',?,?,?)",
                         [(f"p{i}.wav", f"Tema {i}", f"Artista {i % 700}", f"Disco {i % 300}") for i in range(1300)])
        h.db.commit()
        return h
    unico = catalogo.sync(poblar(), batch=10 ** 6)
    host = poblar()
    stop, turnos, res = threading.Event(), [0], {}

    def otro():
        while not stop.is_set():
            with host.db_lock:
                turnos[0] += 1

    t = threading.Thread(target=otro)
    t.start()
    try:
        res["r"] = catalogo.sync(host, batch=500)
    finally:
        stop.set()
        t.join()
    assert res["r"] == unico and unico["piezas"] == 1300
    assert turnos[0] >= 2                                       # entre lotes otro hilo consiguió el lock
    assert catalogo.sync(host, batch=500) == {"artistas": 0, "albumes": 0, "piezas": 0}


def test_listados_paginados_usan_indices():
    host = sdk.Host(":memory:")
    estaciones.register_all(host)
    consultas = [
        "SELECT * FROM assets WHERE status = 'active' ORDER BY title, id LIMIT 50 OFFSET 0",
        "SELECT * FROM artista WHERE archived = 0 ORDER BY nombre, id LIMIT 50 OFFSET 0",
        "SELECT * FROM album WHERE archived = 0 ORDER BY titulo, id LIMIT 50 OFFSET 0",
        "SELECT * FROM genero WHERE archived = 0 ORDER BY nombre, id LIMIT 50 OFFSET 0",
        "SELECT * FROM album WHERE artista_id = 1",
        "SELECT * FROM assets WHERE genero_id = 1",
    ]
    for q in consultas:
        plan = " | ".join(r["detail"] for r in host.db.execute("EXPLAIN QUERY PLAN " + q))
        assert "TEMP B-TREE" not in plan and ("USING" in plan), (q, plan)
