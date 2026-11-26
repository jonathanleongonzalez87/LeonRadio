import csv

from leonradio_core import db, library, playlog


def make_station(tmp_path):
    root = tmp_path / "Rockland Radio"
    (root / "Música" / "20s").mkdir(parents=True)
    (root / "Vestido General" / "Jingles").mkdir(parents=True)
    (root / "Música" / "20s" / "Brilla - Providencia.mp3").write_bytes(b"AAA")
    (root / "Música" / "20s" / "Copia de Brilla - Providencia.mp3").write_bytes(b"AAA")
    (root / "Vestido General" / "Jingles" / "RRC Jingle 1.wav").write_bytes(b"BBB")
    return root


def test_scan_classifies_and_detects_duplicates(tmp_path):
    conn = db.connect()
    stats = library.scan(conn, make_station(tmp_path))
    assert (stats["added"], stats["duplicates"]) == (3, 1)
    row = conn.execute("SELECT * FROM assets WHERE title = 'Brilla' AND status='active'").fetchone()
    assert (row["kind"], row["decade"], row["artist"]) == ("music", "20s", "Providencia")
    assert conn.execute("SELECT kind FROM assets WHERE title LIKE 'RRC%'").fetchone()[0] == "jingle"


def test_playlog_snapshot_survives_asset_edit_and_exports(tmp_path):
    conn = db.connect()
    library.scan(conn, make_station(tmp_path))
    aid = conn.execute("SELECT id FROM assets WHERE kind='music' AND status='active'").fetchone()[0]
    playlog.record_play(conn, station="RRC", asset_id=aid, started_at="2026-11-25T10:00:00Z", played_ms=1000)
    conn.execute("UPDATE assets SET title = 'EDITADO' WHERE id = ?", (aid,))
    out = tmp_path / "music.csv"
    n = playlog.export_csv(conn, out, "2026-11-25T00:00:00Z", "2026-11-26T00:00:00Z", kinds=("music",))
    assert n == 1
    rows = list(csv.DictReader(open(out, encoding="utf-8-sig")))
    assert rows[0]["title"] == "Brilla"  # el historial no cambia al editar el asset


def test_commitment_compliance():
    conn = db.connect()
    conn.execute("INSERT INTO commitments (id, client, plays_required, window_start, window_end)"
                 " VALUES (1,'Cliente X',2,'2026-11-01T00:00:00Z','2026-12-01T00:00:00Z')")
    playlog.record_play(conn, station="RRC", kind="spot", title="Cuña X", commitment_id=1,
                        started_at="2026-11-10T09:00:00Z")
    st = playlog.commitment_status(conn, 1)
    assert (st["delivered"], st["missing"], st["complete"]) == (1, 1, False)
