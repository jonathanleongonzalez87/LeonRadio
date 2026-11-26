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


def test_remove_and_move_files_in_a_list():
    host, playout = plain_host()
    ids = [insert(host, "music", t, 5) for t in ("A", "B", "C")]
    for i in ids:
        playout.add_to("aux2", i)
    titles = lambda: [x["title"] for x in host.state["aux.2"]["queue"]]
    uid = lambda n: host.state["aux.2"]["queue"][n]["uid"]
    assert playout.move("aux2", uid(2), -1) and titles() == ["A", "C", "B"]
    assert not playout.move("aux2", uid(0), -1)                            # ya está arriba
    assert playout.move("aux2", uid(0), 5) and titles() == ["C", "B", "A"]  # se limita al final
    assert playout.remove("aux2", uid(1)) and titles() == ["C", "A"]
    assert not playout.remove("aux2", "no-existe")


def test_drag_move_to_stop_after_and_cart_toggle():
    host, playout = plain_host()
    ids = [insert(host, "music", t, 3) for t in ("A", "B", "C")]
    for i in ids:
        playout.add_to("emision", i)
    q = lambda: [x["title"] for x in host.state["playout.queue"]]
    uid = lambda n: host.state["playout.queue"][n]["uid"]
    assert playout.move_to("emision", uid(0), 2) and q() == ["B", "C", "A"]      # arrastrar el primero al final
    assert playout.move_to("emision", uid(2), 0) and q() == ["A", "B", "C"]
    playout.transport("emision", "play")
    playout.transport("emision", "stop_after")
    assert host.state["playout.stop_after"] is True
    run(playout, 4)                                                              # la actual (3 s) termina
    assert host.state["playout.playing"] is False and host.state["playout.now"] is None
    assert q() == ["B", "C"] and host.state["playout.stop_after"] is False
    jingle = insert(host, "jingle", "Jingle", 5)                                 # botonera: pulsar dos veces detiene
    playout.fire_cart(jingle); playout.tick(0.05)
    assert host.state["cart.active"] == [jingle]
    assert playout.fire_cart(jingle) == {"stopped": True}
    assert host.state["cart.active"] == []


def test_metadata_card_follows_the_selected_file():
    host, playout = plain_host()
    playout.add_to("emision", insert(host, "music", "Tema", 3))
    playout.tick(0.05)
    assert host.state["meta.info"]["title"] == "Tema"                            # sin elegir: el primero de la Emisión
    other = insert(host, "music", "Otro", 3)
    playout.add_to("aux1", other)
    playout.select("aux1", host.state["aux.1"]["queue"][0]["uid"])
    assert host.state["meta.info"]["title"] == "Otro"


def _texts(node):
    out = [node.get("text", "")]
    for c in node.get("children", []):
        out += _texts(c)
    return out


def test_aux_list_has_stop_after_and_proxima_empties_when_armed():
    host, playout = plain_host()
    for t in ("A", "B"):
        playout.add_to("aux1", insert(host, "music", t, 3))
    playout.transport("aux1", "play")
    host.run_command("aux.stop_after", {"n": 1})
    assert host.state["aux.1"]["stop_after"] is True
    run(playout, 4)
    assert host.state["aux.1"]["playing"] is False and host.state["aux.1"]["stop_after"] is False
    assert [x["title"] for x in host.state["aux.1"]["queue"]] == ["B"]           # la siguiente queda cargada, sin sonar
    playout.add_to("emision", insert(host, "music", "Tema", 30))
    playout.transport("emision", "play")
    playout.transport("emision", "stop_after")
    assert "Tema" not in " ".join(_texts(host.draw_editor("proxima")))
    assert "Parará" in " ".join(_texts(host.draw_editor("proxima")))


def test_seek_jumps_inside_the_current_file_and_local_files_can_be_added(tmp_path):
    host, playout = plain_host()
    playout.add_to("emision", insert(host, "music", "Larga", 60))
    playout.transport("emision", "play")
    run(playout, 1)
    assert playout.seek("emision", 30_000)
    playout.tick(0.05)
    assert 30_000 <= host.state["playout.now"]["elapsed_ms"] <= 31_000
    assert not playout.seek("aux1", 5_000)                                   # nada sonando ahí
    wav(tmp_path / "Suelto - Alguien.wav", 1.0)
    aid = library.add_file(host.db, tmp_path / "Suelto - Alguien.wav", host.db_lock)
    assert library.add_file(host.db, tmp_path / "Suelto - Alguien.wav", host.db_lock) == aid    # no duplica
    playout.add_to("aux1", aid)
    assert host.state["aux.1"]["queue"][0]["title"] == "Suelto" and host.state["aux.1"]["queue"][0]["artist"] == "Alguien"


def test_disk_explorer_navigates_and_loads_local_files(tmp_path):
    host, playout = plain_host()
    sub = tmp_path / "Mis cosas"
    sub.mkdir()
    wav(tmp_path / "Uno - Autor.wav", 1.0); wav(tmp_path / "Dos - Autor.wav", 1.3)
    host.run_command("explorer.mode", {"mode": "disk"})
    host.run_command("explorer.cd", {"path": str(tmp_path)})
    tree = host.draw_editor("explorador")
    labels = [n.get("label", "") for n in _all(tree) if n["t"] == "button"]
    assert "📁 Mis cosas" in labels and any("Agregar los 2 audios" in l for l in labels)
    host.run_command("list.add_path", {"path": str(tmp_path / "Uno - Autor.wav")})
    assert host.state["playout.queue"][-1]["title"] == "Uno"
    host.run_command("explorer.add_folder", {"path": str(tmp_path)})
    assert [x["title"] for x in host.state["playout.queue"]][-2:] == ["Dos", "Uno"]
    host.run_command("varios.add", {"editor": "metadatos"})
    tabs = next(n for n in _all(host.draw_editor("varios")) if n["t"] == "tabs")
    assert "Metadatos" in [t["label"] for t in tabs["tabs"]]
    host.run_command("varios.remove", {"editor": "botonera"})
    tabs = next(n for n in _all(host.draw_editor("varios")) if n["t"] == "tabs")
    assert "Botonera" not in [t["label"] for t in tabs["tabs"]]


def _all(node):
    yield node
    for c in node.get("children", []):
        yield from _all(c)
    for t in node.get("tabs", []):
        yield from _all(t)


def test_navegador_is_a_tab_of_varios_and_aire_shows_remaining_time():
    host, playout = plain_host()
    playout.add_to("emision", insert(host, "music", "Tema", 60))
    playout.transport("emision", "play")
    run(playout, 1)
    tree = host.draw_editor("varios")
    tabs = next(n for n in _all(tree) if n["t"] == "tabs")
    assert "Navegador" in [t["label"] for t in tabs["tabs"]]
    assert any(n["t"] == "custom" and n["component"] == "web-browser" for n in _all({"children": tabs["tabs"][3]["children"]}) if "t" in n)
    texts = [n.get("text") for n in _all(host.draw_editor("aire")) if n["t"] == "label"]
    assert "Tiempo restante" in texts and any(t and t.endswith("·  Acaba a las") or t == "·  Acaba a las" for t in texts)


def test_audio_routing_plan_buses_and_saved_settings(tmp_path, monkeypatch):
    from leonradio_core import settings
    from leonradio_core.engine.output import plan_groups

    # sin dispositivos propios: todo sale por el principal
    assert plan_groups({}) == {None: frozenset({"main", "aux1", "aux2", "aux3", "aux4", "cart"})}
    g = plan_groups({"main": "A|WASAPI", "aux2": "B|WASAPI", "cart": "A|WASAPI"})
    assert g["A|WASAPI"] == frozenset({"main", "aux1", "aux3", "aux4", "cart"}) and g["B|WASAPI"] == frozenset({"aux2"})
    # cada salida mezcla solo sus buses
    host, playout = plain_host()
    playout.add_to("emision", insert(host, "music", "Principal", 5))
    playout.add_to("aux2", insert(host, "music", "Dos", 5))
    playout.transport("emision", "play"); playout.transport("aux2", "play")
    only_aux2 = playout.engine.render(4410, frozenset({"aux2"}))
    only_main = playout.engine.render(4410, frozenset({"main"}))
    assert abs(only_aux2).max() > 0.01 and abs(only_main).max() > 0.01
    assert playout.engine.decks["emision"].current.pos == 2 * 4410 or playout.engine.decks["emision"].current.pos == 4410
    # ajustes guardados
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "cfg.json"))
    settings.save({"audio": {"routes": {"main": "X|WASAPI"}}})
    assert settings.load()["audio"]["routes"]["main"] == "X|WASAPI"
    playout.set_input("line1", "Mic|MME")
    assert settings.load()["audio"]["inputs"] == {"line1": "Mic|MME"} and host.state["audio.inputs"] == {"line1": "Mic|MME"}
    with pytest.raises(ValueError):
        playout.set_route("main", "X|WASAPI")                                # modo simulado: sin tarjeta real


class FakeIcecast:
    """Servidor Icecast mínimo: acepta PUT con contraseña y cuenta los bytes; anota las peticiones de metadatos."""

    def __init__(self, password="hackme"):
        import socket
        import threading

        self.password, self.received, self.heads, self.meta = password, 0, [], []
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(5)
        self.port = self.srv.getsockname()[1]
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        import base64
        import threading

        while True:
            try:
                conn, _ = self.srv.accept()
            except OSError:
                return

            def handle(c=conn):
                buf = b""
                while b"\r\n\r\n" not in buf:
                    d = c.recv(4096)
                    if not d:
                        return
                    buf += d
                head, _, rest = buf.partition(b"\r\n\r\n")
                text = head.decode("latin-1")
                ok = base64.b64encode(f"source:{self.password}".encode()).decode() in text
                if text.startswith("GET /admin/metadata"):
                    self.meta.append(text.split("\r\n")[0])
                    c.sendall(b"HTTP/1.0 200 OK\r\n\r\n")
                    return
                if not ok:
                    c.sendall(b"HTTP/1.0 401 Unauthorized\r\n\r\n")
                    return
                self.heads.append(text)
                c.sendall(b"HTTP/1.1 100 Continue\r\n\r\n")
                self.received += len(rest)
                while True:
                    d = c.recv(65536)
                    if not d:
                        return
                    self.received += len(d)

            threading.Thread(target=handle, daemon=True).start()


def test_streaming_to_icecast_sends_mp3_metadata_and_never_exposes_the_password(tmp_path, monkeypatch):
    import time

    pytest.importorskip("lameenc")
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "cfg.json"))
    host, playout = plain_host()
    ice = FakeIcecast()
    playout.stream_set(host="127.0.0.1", port=ice.port, mount="radio", password="hackme", name="RRC", bitrate=96)
    assert "password" not in host.state["stream.config"] and host.state["stream.config"]["has_password"] is True
    assert host.state["stream.config"]["mount"] == "/radio"
    playout.add_to("emision", insert(host, "music", "Tema", 30))
    playout.transport("emision", "play")
    playout.stream_do("connect")
    run(playout, 3)
    for _ in range(40):                                                   # el hilo de envío trabaja aparte
        if ice.received > 2000 and ice.meta:
            break
        time.sleep(0.05)
    assert host.state["stream.status"]["state"] == "live"
    assert ice.received > 2000
    head = ice.heads[0]
    assert head.startswith("PUT /radio HTTP/1.1") and "ice-name: RRC" in head and "ice-bitrate: 96" in head
    assert ice.meta and "song=Tema" in ice.meta[0]
    playout.stream_do("disconnect")
    time.sleep(0.5)
    assert playout.stream.status()["state"] == "stopped"
    # contraseña incorrecta: error claro y no reintenta
    playout.stream_set(password="otra")
    playout.stream_do("connect")
    for _ in range(40):
        if playout.stream.status()["state"] == "error":
            break
        time.sleep(0.05)
    assert playout.stream.status()["state"] == "error" and "contraseña" in playout.stream.status()["message"]
    playout.stream.shutdown()


def test_streaming_records_to_a_file_without_a_server(tmp_path, monkeypatch):
    import time

    pytest.importorskip("lameenc")
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "cfg.json"))
    host, playout = plain_host()
    playout.stream_set(record_dir=str(tmp_path / "rec"))
    playout.add_to("emision", insert(host, "music", "Tema", 30))
    playout.transport("emision", "play")
    playout.stream_do("record")
    run(playout, 2)
    time.sleep(0.6)
    files = list((tmp_path / "rec").glob("*.mp3"))
    assert len(files) == 1 and files[0].stat().st_size > 1000
    playout.stream_do("record")
    time.sleep(0.5)
    assert playout.stream.status()["recording"] is False
    playout.stream.shutdown()


def test_monitor_websocket_streams_the_main_mix_as_pcm(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from leonradio_core import server

    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "cfg.json"))
    app = server.create_app(audio="null", tick=True)
    with TestClient(app) as client:                                          # arranca el reloj del Playout
        pl = app.state.playout
        pl.add_to("emision", insert(app.state.host, "music", "Tema", 30))
        pl.transport("emision", "play")
        with client.websocket_connect("/ws/monitor") as ws:
            head = ws.receive_json()
            assert head == {"rate": 44100, "channels": 2}
            blocks = [ws.receive_bytes() for _ in range(3)]
    assert all(len(b) % 4 == 0 and len(b) > 0 for b in blocks)                # int16 estéreo: 4 bytes por fotograma
    assert any(max(abs(int.from_bytes(b[i:i + 2], "little", signed=True)) for i in range(0, len(b), 2)) > 100
               for b in blocks)                                              # hay señal, no solo silencio
