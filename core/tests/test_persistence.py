"""Base persistente: migraciones, copias de seguridad, escaneo incremental y ruta de la base."""

import os
import sqlite3
import wave
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from leonradio_core import backup, db, library, playlog, sdk, settings
from leonradio_core.server import create_app


def wav(path, seconds=0.2, rate=8000, freq=330):
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.4 * 32767 * np.sin(2 * np.pi * freq * t)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())


def make_root(tmp_path):
    root = tmp_path / "Radio"
    for i, name in enumerate(["A - X.wav", "B - Y.wav", "C - Z.wav"]):
        wav(root / "Música" / "20s" / name, freq=300 + 50 * i)
    return root


def old_schema_file(path, with_file_type=True):
    """Base creada a mano con el esquema original (sin user_version)."""
    schema = db.SCHEMA_V1
    if not with_file_type:
        line = "    file_type     TEXT NOT NULL DEFAULT 'audio' CHECK (file_type IN ('audio','event','other')),\n"
        assert line in schema
        schema = schema.replace(line, "")
    conn = sqlite3.connect(str(path))
    conn.executescript(schema)
    conn.execute("INSERT INTO assets (id, path, kind, title) VALUES (1, 'x.wav', 'music', 'Vieja')")
    conn.execute("INSERT INTO playlog (station, started_at, asset_id, kind, title) "
                 "VALUES ('RRC','2026-01-01T00:00:00Z',1,'music','Vieja')")
    conn.commit()
    conn.close()


def count(path, table):
    c = sqlite3.connect(str(path))
    try:
        return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        c.close()


# -- persistencia y migraciones ---------------------------------------------------------

def test_base_persiste_al_reiniciar(tmp_path):
    f = tmp_path / "x.db"
    host = sdk.Host(db_path=str(f))
    with host.db_lock:
        host.db.execute("INSERT INTO assets (path, kind, title) VALUES ('a.wav','music','Tema')")
        aid = host.db.execute("SELECT id FROM assets").fetchone()[0]
        playlog.record_play(host.db, station="RRC", asset_id=aid, started_at="2026-11-25T10:00:00Z", played_ms=1000)
        db.close(host.db)
    host2 = sdk.Host(db_path=str(f))
    assert host2.db.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 1
    assert host2.db.execute("SELECT title FROM playlog").fetchone()[0] == "Tema"
    db.close(host2.db)


@pytest.mark.parametrize("con_file_type", [True, False])
def test_migracion_desde_esquema_viejo(tmp_path, con_file_type):
    f = tmp_path / "vieja.db"
    old_schema_file(f, con_file_type)
    conn = db.connect(f)
    assert db.version(conn) == len(db.MIGRATIONS)
    assert conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 1
    row = conn.execute("SELECT title, file_type FROM playlog").fetchone()
    assert (row["title"], row["file_type"]) == ("Vieja", "audio")
    assert {"size_bytes", "mtime_ns"} <= {r["name"] for r in conn.execute("PRAGMA table_info(assets)")}
    db.close(conn)


def test_migracion_falla_revierte(tmp_path, monkeypatch):
    def rota(conn):
        conn.execute("CREATE TABLE a_medias (x INTEGER)")
        raise ValueError("falla a mitad")
    f = tmp_path / "m.db"
    db.close(db.connect(f))
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, rota])
    with pytest.raises(ValueError):
        db.connect(f)
    c = sqlite3.connect(str(f))
    assert c.execute("PRAGMA user_version").fetchone()[0] == 2
    assert c.execute("SELECT name FROM sqlite_master WHERE name = 'a_medias'").fetchone() is None
    c.close()


def test_version_futura_rechazada(tmp_path):
    f = tmp_path / "f.db"
    c = sqlite3.connect(str(f))
    c.execute("CREATE TABLE t (x)")
    c.execute("PRAGMA user_version = 999")
    c.commit(); c.close()
    antes = f.read_bytes()
    with pytest.raises(RuntimeError, match="versión más nueva"):
        db.connect(f)
    assert f.read_bytes() == antes
    assert not (tmp_path / "f.db-wal").exists()


# -- copias de seguridad -------------------------------------------------------------------

def test_copia_consistente(tmp_path):
    f = tmp_path / "b.db"
    conn = db.connect(f, shared=True)
    conn.executemany("INSERT INTO assets (path, kind, title) VALUES (?, 'music', ?)",
                     [(f"{i}.wav", f"T{i}") for i in range(5)])
    conn.commit()
    conn.execute("INSERT INTO assets (path, kind, title) VALUES ('pendiente.wav','music','P')")   # sin commit
    other = sqlite3.connect(str(f))                                  # otra conexión WAL abierta
    out = backup.make_backup(f)
    assert out is not None and out.parent == tmp_path / "copias" and out.name.startswith("leonradio-")
    assert count(out, "assets") == 5
    other.close(); db.close(conn)


def test_rotacion_conserva_7(tmp_path):
    f = tmp_path / "r.db"
    db.close(db.connect(f))
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    ajeno = tmp_path / "copias" / "notas.txt"
    ajeno.parent.mkdir()
    ajeno.write_text("mío")
    for i in range(10):
        assert backup.make_backup(f, min_interval_s=0, now=base + timedelta(minutes=i)) is not None
    names = sorted(p.name for p in (tmp_path / "copias").glob("leonradio-*.db"))
    assert len(names) == 7
    assert names[0] == "leonradio-20260101-000300.db" and names[-1] == "leonradio-20260101-000900.db"
    assert ajeno.read_text() == "mío"


def test_copia_omitida_si_base_nueva_o_reciente(tmp_path, monkeypatch):
    f = tmp_path / "o.db"
    assert backup.make_backup(f) is None                              # no existe
    assert backup.make_backup(":memory:") is None
    db.close(db.connect(f))
    now = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
    assert backup.make_backup(f, now=now) is not None
    assert backup.make_backup(f, now=now + timedelta(minutes=10)) is None      # < 1 h
    assert backup.make_backup(f, now=now + timedelta(minutes=10), force=True) is not None
    monkeypatch.setattr(db, "MIGRATIONS", [*db.MIGRATIONS, lambda c: None])   # migración pendiente
    assert backup.make_backup(f, now=now + timedelta(minutes=20)) is not None


def test_fallo_de_copia_no_impide_arrancar(tmp_path):
    f = tmp_path / "e.db"
    db.close(db.connect(f))
    (tmp_path / "copias").write_text("soy un archivo")
    assert backup.make_backup(f) is None                              # no lanza


# -- escaneo incremental --------------------------------------------------------------------

def ids(conn):
    return {r["path"]: r["id"] for r in conn.execute("SELECT id, path FROM assets")}


def test_escaneo_incremental(tmp_path):
    root = make_root(tmp_path)
    conn = db.connect()
    assert library.scan(conn, root)["added"] == 3
    first = ids(conn)
    r = library.scan(conn, root)
    assert (r["unchanged"], r["added"]) == (3, 0) and ids(conn) == first

    victim = root / "Música" / "20s" / "A - X.wav"
    aid = first[str(victim)]
    playlog.record_play(conn, station="RRC", asset_id=aid, started_at="2026-11-25T10:00:00Z", played_ms=1)
    saved = victim.read_bytes()
    st = os.stat(victim)
    victim.unlink()
    assert library.scan(conn, root)["retired"] == 1
    assert conn.execute("SELECT status FROM assets WHERE id = ?", (aid,)).fetchone()[0] == "retired"
    assert conn.execute("SELECT asset_id FROM playlog").fetchone()[0] == aid

    victim.write_bytes(saved)
    os.utime(victim, ns=(st.st_atime_ns, st.st_mtime_ns))             # mismo tamaño y fecha: vuelve sin releer
    r = library.scan(conn, root)
    assert (r["reactivated"], r["updated"]) == (1, 0) and ids(conn)[str(victim)] == aid
    assert conn.execute("SELECT status FROM assets WHERE id = ?", (aid,)).fetchone()[0] == "active"

    old = conn.execute("SELECT sha256 FROM assets WHERE id = ?", (aid,)).fetchone()[0]
    wav(victim, seconds=0.5)
    assert library.scan(conn, root)["updated"] == 1
    assert conn.execute("SELECT sha256 FROM assets WHERE id = ?", (aid,)).fetchone()[0] != old
    assert ids(conn)[str(victim)] == aid

    wav(root / "Música" / "20s" / "D - W.wav", freq=900)
    assert library.scan(conn, root)["added"] == 1


def test_escaneo_rellena_filas_previas_sin_releer(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    conn = db.connect()
    library.scan(conn, root)
    conn.execute("UPDATE assets SET size_bytes = NULL, mtime_ns = NULL")
    monkeypatch.setattr(library, "sha256_of", lambda p: pytest.fail("no debe re-hashear"))
    r = library.scan(conn, root)
    assert r["unchanged"] == 3
    assert conn.execute("SELECT COUNT(*) FROM assets WHERE size_bytes IS NULL").fetchone()[0] == 0


def test_escaneo_no_retira_si_carpeta_falta(tmp_path):
    root = make_root(tmp_path)
    conn = db.connect()
    library.scan(conn, root)
    root.rename(tmp_path / "otra")
    assert library.scan(conn, root)["retired"] == 0
    (tmp_path / "otra").rename(root)
    for p in root.rglob("*.wav"):
        p.unlink()
    assert library.scan(conn, root)["retired"] == 0                  # carpeta vacía de golpe
    assert conn.execute("SELECT COUNT(*) FROM assets WHERE status = 'active'").fetchone()[0] == 3


def test_escaneo_no_toca_piezas_externas(tmp_path):
    root = make_root(tmp_path)
    conn = db.connect()
    wav(tmp_path / "Suelta - Otro.wav", freq=777)
    ext = library.add_file(conn, tmp_path / "Suelta - Otro.wav")
    library.scan(conn, root)
    wav(root / "Música" / "20s" / "E - V.wav", freq=640)
    r = library.scan(conn, root)
    assert r["retired"] == 0
    assert conn.execute("SELECT status FROM assets WHERE id = ?", (ext,)).fetchone()[0] == "active"


def test_escaneo_cancelable(tmp_path):
    root = make_root(tmp_path)
    conn = db.connect()
    calls = []

    def cancel():
        calls.append(1)
        return len(calls) > 2                                         # cancela al tercer archivo
    r = library.scan(conn, root, cancel=cancel)
    assert r["cancelled"] and r["added"] == 2 and r["retired"] == 0
    r = library.scan(conn, root)
    assert (r["added"], r["unchanged"], r["cancelled"]) == (1, 2, False)


# -- ruta de la base ------------------------------------------------------------------------

def test_db_path_precedencia(tmp_path, monkeypatch):
    for v in ("LEONRADIO_DB", "LEONRADIO_CONFIG", "LOCALAPPDATA"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert settings.db_path() == tmp_path / "local" / "LeonRadio" / "leonradio.db"
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "cfg" / "config.json"))
    assert settings.db_path() == tmp_path / "cfg" / "leonradio.db"
    monkeypatch.setenv("LEONRADIO_DB", str(tmp_path / "env.db"))
    assert settings.db_path() == tmp_path / "env.db"
    assert settings.db_path(tmp_path / "arg.db") == tmp_path / "arg.db"


def test_pruebas_no_tocan_base_real(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("LEONRADIO_DB", raising=False)
    monkeypatch.delenv("LEONRADIO_CONFIG", raising=False)
    create_app()
    sdk.Host()
    assert not (tmp_path / "LeonRadio").exists()


def test_cierre_del_servidor_deja_un_solo_archivo(tmp_path):
    from fastapi.testclient import TestClient
    f = tmp_path / "s.db"
    app = create_app(db_path=str(f), tick=False)
    with TestClient(app):
        with app.state.host.db_lock:
            app.state.host.db.execute("INSERT INTO assets (path, kind, title) VALUES ('a.wav','music','T')")
            app.state.host.db.commit()
    assert count(f, "assets") == 1
    assert not (tmp_path / "s.db-wal").exists() or (tmp_path / "s.db-wal").stat().st_size == 0


def test_copia_con_base_danada_no_rota(tmp_path, monkeypatch):
    f = tmp_path / "q.db"
    db.close(db.connect(f))
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(3):
        backup.make_backup(f, min_interval_s=0, now=base + timedelta(minutes=i))
    real = sqlite3.Connection

    class Mala(real):
        def execute(self, sql, *a):
            if "quick_check" in sql:
                return real.execute(self, "SELECT 'corrupta'")
            return real.execute(self, sql, *a)
    monkeypatch.setattr(backup.sqlite3, "connect", lambda p, **k: Mala(p, **k))
    assert backup.make_backup(f, keep=1, min_interval_s=0, now=base + timedelta(minutes=9)) is None
    copias = tmp_path / "copias"
    assert len(list(copias.glob("leonradio-*.db"))) == 3 and not list(copias.glob("*.tmp"))


def test_copia_mismo_segundo_no_pisa(tmp_path):
    f = tmp_path / "u.db"
    db.close(db.connect(f))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = backup.make_backup(f, min_interval_s=0, now=now)
    b = backup.make_backup(f, min_interval_s=0, now=now)
    assert a != b and a.exists() and b.exists()


def test_scan_cli_base_futura_mensaje_claro(tmp_path):
    from leonradio_core import cli
    f = tmp_path / "f.db"
    c = sqlite3.connect(str(f)); c.execute("PRAGMA user_version = 999"); c.close()
    with pytest.raises(SystemExit) as e:
        cli.main(["scan", str(tmp_path), "--db", str(f)])
    assert "versión más nueva" in str(e.value)
    g = tmp_path / "g.db"
    g.write_bytes(b"esto no es una base de datos sqlite" * 50)
    with pytest.raises(SystemExit) as e:
        cli.main(["scan", str(tmp_path), "--db", str(g)])
    assert "no se pudo abrir" in str(e.value)


def test_escaneo_ignora_directorios_con_extension_de_audio(tmp_path):
    root = make_root(tmp_path)
    (root / "carpeta.mp3").mkdir()
    assert library.scan(db.connect(), root)["added"] == 3
