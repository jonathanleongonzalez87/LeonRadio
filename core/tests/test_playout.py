"""Playout: las listas, el historial y los ficheros de los tres tipos, con audio simulado o archivos reales."""

import wave

import numpy as np
import pytest

from leonradio_core import builtin, library, sdk
from leonradio_core.engine import event_file
from leonradio_core.engine.output import NullOutput
from leonradio_core.engine.playout import Playout


def wav(path, seconds=1.0, rate=22050):
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.4 * 32767 * np.sin(2 * np.pi * 330 * t)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())


def run(playout, seconds, dt=0.05):
    for _ in range(round(seconds / dt)):
        playout.tick(dt)


def insert(host, kind, title, seconds, path=None):
    with host.db_lock:
        cur = host.db.execute("INSERT INTO assets (path, kind, title, duration_ms) VALUES (?,?,?,?)",
                              (path or f"demo://{title}", kind, title, int(seconds * 1000)))
        host.db.commit()
    return cur.lastrowid


def plain_host():
    """Host sin la emisión de arranque: solo los decks vacíos."""
    host = sdk.Host()
    playout = builtin.register(host, output=NullOutput(), autoplay=False)
    playout.clear("emision")
    return host, playout


def rows(host, where="1=1"):
    return [dict(r) for r in host.db.execute(f"SELECT * FROM playlog WHERE {where} ORDER BY id")]


def test_every_file_type_is_played_and_logged_with_its_file_type():
    host, playout = plain_host()
    pings = []
    host.register_command("test.ping", lambda ctx, n: pings.append(n))
    a = insert(host, "jingle", "RRC Jingle", 1)
    playout.add_to("aux1", a)                                              # audio
    playout.add_to("aux1", "marca-tanda")                                  # evento (marcador)
    playout.add("aux1", event_file("command", "Aviso", command="test.ping", args={"n": 7}))   # evento (comando)
    playout.add_to("aux1", "nota-locutor")                                 # otro (nota)
    playout.add_to("aux1", "pausa-5s")                                     # evento (pausa de 5 s)
    playout.transport("aux1", "play")
    run(playout, 7)
    log = rows(host)
    by_type = {t: [r for r in log if r["file_type"] == t] for t in ("audio", "event", "other")}
    assert len(by_type["audio"]) == 1 and by_type["audio"][0]["played_ms"] == pytest.approx(1000, abs=60)
    assert {r["kind"] for r in by_type["event"]} == {"marker", "command", "pause"}
    assert by_type["other"][0]["kind"] == "note"
    pause = next(r for r in by_type["event"] if r["kind"] == "pause")
    assert pause["played_ms"] == pytest.approx(5000, abs=100) and pause["status"] == "completed"
    assert pings == [7]                                                    # el evento ejecutó su comando
    assert all(r["source"] == "live" for r in log)                         # una auxiliar la opera el locutor


def test_cart_voice_ducks_the_music_and_is_logged_as_cart():
    host, playout = plain_host()
    playout.add_to("emision", insert(host, "music", "Cancion", 30))
    playout.transport("emision", "play")
    run(playout, 1)
    pisador = insert(host, "pisador", "Pisa Rockland", 1.5)
    playout.fire_cart(pisador)
    run(playout, 0.8)
    assert playout.engine.ducking_db < -3                                   # la música bajó
    run(playout, 3)
    assert playout.engine.ducking_db > -1.5                                 # y se recuperó
    cart = rows(host, "source = 'cart'")
    assert len(cart) == 1 and cart[0]["title"] == "Pisa Rockland" and cart[0]["file_type"] == "audio"
    assert host.state["cart.last"]["title"] == "Pisa Rockland"


def test_playlist_m3u_resolves_by_filename_and_reports_missing(tmp_path):
    root = tmp_path / "Radio"
    (root / "Música" / "20s").mkdir(parents=True)
    (root / "Playlists").mkdir()
    wav(root / "Música" / "20s" / "Uno - Banda.wav", 1.0); wav(root / "Música" / "20s" / "Dos - Banda.wav", 1.3)   # distintos: si no, el escáner marca el 2.º como duplicado
    (root / "Playlists" / "lista.m3u").write_text(
        "#EXTM3U\n#EXTINF:1,Uno\nD:\\OTRO PC\\Radio\\Música\\20s\\Uno - Banda.wav\n"
        "/home/x/Dos - Banda.wav\nD:\\no\\esta\\Perdida.wav\n", encoding="utf-8")
    host = sdk.Host()
    host.library_dir = str(root)
    library.scan(host.db, root)
    playout = builtin.register(host, output=NullOutput(), autoplay=False)
    playout.clear("aux2")
    assert [p["name"] for p in sdk.Context(host, "builtin", frozenset(sdk.PERMISSIONS)).playlists()] == ["lista"]
    res = playout.load_m3u("aux2", str(root / "Playlists" / "lista.m3u"))
    assert res == {"added": 2, "missing": 1}
    assert [i["title"] for i in playout.deck("aux2").queue] == ["Uno", "Dos"]
    assert "2 ficheros agregados, 1 no encontrados" in host.state["playout.message"]
    with pytest.raises(ValueError):                                         # fuera de la carpeta de la emisora: no
        playout.load_m3u("aux2", str(tmp_path / "otra.m3u"))


def test_real_files_play_through_the_engine_with_real_levels_and_duration(tmp_path):
    root = tmp_path / "Radio" / "Vestido General" / "Jingles"
    root.mkdir(parents=True)
    wav(root / "Uno.wav", 1.0); wav(root / "Dos.wav", 1.0)
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    playout = builtin.register(host, output=NullOutput(), autoplay=False)
    playout.clear("emision")
    levels = []
    host.events.subscribe(lambda n, d: levels.append(d) if n == "audio.levels" else None)
    for r in host.db.execute("SELECT id FROM assets ORDER BY title").fetchall():
        playout.add_to("emision", r["id"])
    playout.transport("emision", "play")
    run(playout, 2.5)
    log = rows(host)
    assert [r["status"] for r in log] == ["completed", "completed"]
    assert all(r["played_ms"] == pytest.approx(1000, abs=60) for r in log)  # duración real, no la de la etiqueta
    assert max(l["l"] for l in levels) > 0.5                                # VU real: sonó
    assert levels[-1]["l"] < 0.05                                           # y al final queda en silencio
    assert host.state["playout.queue"] == [] and host.state["playout.now"] is None


def test_missing_file_is_logged_as_failed_and_explained(tmp_path):
    host, playout = plain_host()
    a = insert(host, "jingle", "Fantasma", 1, path=str(tmp_path / "no-existe.mp3"))
    b = insert(host, "jingle", "Siguiente", 1)
    playout.add_to("aux3", a); playout.add_to("aux3", b)
    playout.transport("aux3", "play")
    run(playout, 1.5)
    log = rows(host)
    assert [(r["title"], r["status"]) for r in log] == [("Fantasma", "failed"), ("Siguiente", "completed")]
    assert "No se pudo reproducir «Fantasma»" in host.state["playout.message"]


def test_stop_returns_the_file_to_the_top_and_pause_freezes_it():
    host, playout = plain_host()
    playout.add_to("aux4", insert(host, "music", "Larga", 60))
    playout.transport("aux4", "play")
    run(playout, 1)
    assert host.state["aux.4"]["now"]["title"] == "Larga" and host.state["aux.4"]["playing"]
    playout.transport("aux4", "pause")
    run(playout, 0.2)
    pos = playout.deck("aux4").current.pos
    run(playout, 1)
    assert playout.deck("aux4").current.pos == pos and not host.state["aux.4"]["playing"]
    playout.transport("aux4", "stop")
    assert host.state["aux.4"]["now"] is None and [i["title"] for i in playout.deck("aux4").queue] == ["Larga"]
    assert rows(host)[-1]["status"] == "interrupted"


def test_device_failure_falls_back_to_simulated_and_says_so():
    class Broken(NullOutput):
        simulated = False
        driven = False
        name = "Dispositivo roto"

        def start(self, engine):
            raise RuntimeError("dispositivo ocupado")

    host = sdk.Host()
    playout = Playout(host, Broken())
    playout.start()
    assert playout.output.simulated and host.state["audio.info"]["simulated"] is True
    assert "dispositivo ocupado" in host.state["playout.message"]
