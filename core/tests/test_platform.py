import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leonradio_core import addons, builtin, sdk
from leonradio_core.server import create_app
from leonradio_core.uischema import UI

REPO = Path(__file__).resolve().parents[2]


def make_wav(path, seconds=1.0, rate=22050):
    """Audio WAV real (tono de 330 Hz) para pruebas: el motor ahora decodifica de verdad los archivos."""
    import wave
    import numpy as np
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.4 * 32767 * np.sin(2 * np.pi * 330 * t)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())


def test_ui_builder_nests_and_validates():
    ui = UI()
    with ui.row():
        ui.label("a", "accent")
        ui.button("ok", "x.y")
    tree = ui.build()
    assert tree["children"][0]["t"] == "row"
    assert [c["t"] for c in tree["children"][0]["children"]] == ["label", "button"]
    with pytest.raises(ValueError):
        ui.label("x", "inexistente")


def test_builtin_editors_draw_with_demo_playout():
    host = sdk.Host()
    playout = builtin.register(host)
    assert {"aire", "emision", "historial", "proxima", "botonera"} <= set(host.editors)
    tree = host.draw_editor("aire")
    def walk(n):
        yield n["t"]
        for c in n.get("children", []):
            yield from walk(c)
    assert "slider" in set(walk(tree))      # el progreso está (ahora junto a los botones, en una fila)
    host.run_command("playout.next")  # salta con un fundido de 300 ms; al terminar queda registrado como 'skipped'
    playout.tick(0.5)
    plays = host.db.execute("SELECT status FROM playlog").fetchall()
    assert [p["status"] for p in plays] == ["skipped"]


def make_addon(tmp, perms, body):
    d = tmp / "mi_addon"
    d.mkdir()
    (d / "leonradio_addon.toml").write_text(
        f'id="t.a"\nname="T"\nversion="0.1"\napi_version="0.1"\npermissions={perms}\n', encoding="utf-8")
    (d / "__init__.py").write_text(textwrap.dedent(body), encoding="utf-8")
    return d


def test_addon_permissions_are_enforced(tmp_path):
    host = sdk.Host()
    d = make_addon(tmp_path, "[]", """
        import leonradio as lr
        class E(lr.Editor):
            id = "t.e"; label = "E"
            def draw(self, ui, ctx):
                ctx.recent_plays()      # sin permiso playlog.read
        def register(): lr.register_editor(E)
    """)
    addons.load_addon(host, d)
    tree = host.draw_editor("t.e")      # el error se muestra, no tumba la app
    assert "Error" in tree["children"][0]["text"]
    assert "playlog.read" in tree["children"][1]["text"]


def test_addon_rejects_incompatible_api_and_unknown_permission(tmp_path):
    d = make_addon(tmp_path, "[]", "def register(): pass")
    (d / "leonradio_addon.toml").write_text(
        'id="t.a"\nname="T"\nversion="0.1"\napi_version="9.0"\n', encoding="utf-8")
    with pytest.raises(addons.AddonError):
        addons.read_manifest(d)
    (d / "leonradio_addon.toml").write_text(
        'id="t.a"\nname="T"\nversion="0.1"\napi_version="0.1"\npermissions=["root"]\n', encoding="utf-8")
    with pytest.raises(addons.AddonError):
        addons.read_manifest(d)


def test_broken_addon_does_not_stop_startup(tmp_path):
    make_addon(tmp_path, "[]", "raise RuntimeError('boom')")
    host = sdk.Host()
    assert addons.discover(host, tmp_path) == []
    assert "t.e" not in host.editors


def test_api_endpoints_and_example_addon():
    app = create_app(tick=False, ui_dir=Path("/nonexistent"))
    with TestClient(app) as c:
        eds = {e["id"] for e in c.get("/api/editors").json()}
        assert {"aire", "emision", "historial", "ejemplo.hora"} <= eds
        assert c.get("/api/editors/aire/draw").json()["t"] == "column"
        assert c.post("/api/commands/ejemplo.pulsar").json()["result"] == 1
        assert c.post("/api/commands/ejemplo.pulsar").json()["result"] == 2
        assert c.post("/api/commands/no.existe").status_code == 404
        assert c.get("/api/editors/nada/draw").status_code == 404
        info = c.get("/api/info").json()
        assert info["addons"][0]["id"] == "com.leonradio.ejemplo-hora"


def _walk(n):
    if "t" in n:          # las pestañas (dict sin tipo) solo contienen hijos
        yield n
    for c in n.get("children", []):
        yield from _walk(c)
    for t in n.get("tabs", []):
        yield from _walk(t)


def test_vintage_editors_use_custom_components_and_cartwall_fires(tmp_path):
    lib = tmp_path / "Radio" / "Vestido General" / "Jingles"
    lib.mkdir(parents=True)
    make_wav(lib / "Jingle 1.wav")
    from leonradio_core import library
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    playout = builtin.register(host)
    comps = {}
    for ed in ("vu", "reloj", "dial", "botonera"):
        customs = [n for n in _walk(host.draw_editor(ed)) if n["t"] == "custom"]
        assert customs, ed
        comps[ed] = customs
    assert comps["vu"][0]["component"] == "vu-meter"
    assert comps["reloj"][0]["props"]["timezone"] == "America/Bogota"
    assert comps["dial"][0]["props"]["name"] == "RRC"
    cart = next(c for c in comps["botonera"] if c["component"] == "cartwall")
    pad = cart["props"]["pads"][0]
    assert pad["key"] == "1" and pad["style"] == "orange"
    host.run_command("cart.fire", {"asset_id": pad["asset_id"]})
    playout.tick(1.5)                                   # el jingle dura 1 s: al terminar queda en el historial
    row = host.db.execute("SELECT source, title FROM playlog WHERE source = 'cart'").fetchone()
    assert (row["source"], row["title"]) == ("cart", "Jingle 1")   # la Emisión (auto) también suena: se filtra la botonera


def test_demo_playout_emits_levels_and_ticks_once_per_second():
    host = sdk.Host()
    playout = builtin.register(host)
    seen = []
    host.events.subscribe(lambda n, d: seen.append(n))
    for _ in range(10):
        playout.tick(0.1)
    assert seen.count("audio.levels") == 10
    assert seen.count("state_changed") <= 2  # playout.now se publica ~1 vez por segundo
    levels = []
    host.events.subscribe(lambda n, d: levels.append(d) if n == "audio.levels" else None)
    playout.tick(0.1)
    assert 0.0 <= levels[-1]["l"] <= 1.0 and 0.0 <= levels[-1]["r"] <= 1.0



def test_varios_has_tabs_events_and_explorer(tmp_path):
    lib = tmp_path / "Radio" / "Música" / "20s"
    lib.mkdir(parents=True)
    (lib / "Brilla - Providencia.mp3").write_bytes(b"A")
    from leonradio_core import library
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    builtin.register(host)
    tabs = next(n for n in _walk(host.draw_editor("varios")) if n["t"] == "tabs")
    assert [t["label"] for t in tabs["tabs"]] == ["Botonera", "Eventos", "Explorador", "Navegador", "Streaming", "＋"]
    events = next(n for n in _walk(tabs["tabs"][1]) if n["t"] == "custom")
    assert events["component"] == "event-list" and len(events["props"]["events"]) >= 3
    explorer = tabs["tabs"][2]
    buttons = [n for n in _walk(explorer) if n["t"] == "button"]
    assert any(b["selected"] and b["command"] == "explorer.group" for b in buttons)   # grupo activo
    assert any(b["label"] == "Emisión" and b["selected"] for b in buttons)            # destino por defecto
    assert any(b["command"] == "list.add" for b in buttons)                           # botón ＋


def test_explorer_sends_to_emision_and_auxiliares(tmp_path):
    lib = tmp_path / "Radio" / "Música" / "20s"
    lib.mkdir(parents=True)
    make_wav(lib / "Brilla - Providencia.wav")
    from leonradio_core import library
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    builtin.register(host)
    aid = host.db.execute("SELECT id FROM assets").fetchone()[0]
    before = len(host.state["playout.queue"])
    host.run_command("list.add", {"asset_id": aid})                       # destino por defecto: emisión
    assert len(host.state["playout.queue"]) == before + 1
    host.run_command("explorer.target", {"target": "aux3"})
    host.run_command("list.add", {"asset_id": aid})
    assert [x["title"] for x in host.state["aux.3"]["queue"]] == ["Brilla"]
    host.run_command("aux.play", {"n": 3})
    assert host.state["aux.3"]["playing"] and host.state["aux.3"]["now"]["title"] == "Brilla"
    host.run_command("aux.pause", {"n": 3})
    assert not host.state["aux.3"]["playing"]
    tree = host.draw_editor("aux3")
    assert any(n["t"] == "slider" for n in _walk(tree))
    assert {"aux1", "aux2", "aux3", "aux4"} <= set(host.editors)


def test_root_redirects_to_versioned_ui_url(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>LeonRadio</title>", encoding="utf-8")
    app = create_app(tick=False, ui_dir=tmp_path, addon_dirs=[])
    with TestClient(app) as c:
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"].startswith("/v/v")
        page = c.get(r.headers["location"])
        assert page.status_code == 200 and "LeonRadio" in page.text
        assert page.headers["cache-control"] == "no-cache"
        assert c.get("/api/editors").status_code == 200      # la API no se ve afectada


def test_demo_backend_runs_the_real_engine_in_memory():
    import json
    from leonradio_core.demo_web import create
    be = create(str(REPO))                                    # lee el addon de ejemplo de <repo>/addons
    assert json.loads(be.info())["station"] == "RRC"
    ids = {e["id"] for e in json.loads(be.editors())}
    assert {"aire", "emision", "botonera", "aux1", "ejemplo.hora"} <= ids
    assert json.loads(be.draw("emision"))["t"] == "column"
    assert "error" in json.loads(be.draw("no-existe"))
    assert json.loads(be.run("playout.pause"))["ok"] is True
    assert json.loads(be.run("no.existe"))["ok"] is False
    events = json.loads(be.tick(0.1))                         # los eventos llegan por lotes
    assert any(e["event"] == "audio.levels" for e in events)


def test_build_demo_bundles_ui_and_engine_into_one_file(tmp_path):
    import importlib.util
    spec = importlib.util.spec_from_file_location("build_demo", REPO / "tools" / "build_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.OUT = tmp_path / "demo.html"
    mod.main()
    html = mod.OUT.read_text(encoding="utf-8")
    for needle in ("lr-py-files", "LR_DEMO_BACKEND", "const m_main_js", "leonradio_core/demo_web.py",
                   "addons/ejemplo_hora_emisora/leonradio_addon.toml", "data:font/woff2;base64"):
        assert needle in html, needle
    bundle = html[html.index("const m_api_js"):]
    assert "\nimport {" not in bundle and "\nexport " not in bundle      # módulos ES ya resueltos
    assert 'type="module"' not in html                                   # sin módulos: abre con doble clic
    assert "leonradio_core/server.py" not in html                        # el servidor no va al navegador


def test_legacy_paths_still_served_for_stale_cached_pages(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>LeonRadio</title>", encoding="utf-8")
    (tmp_path / "app.css").write_text("body{}", encoding="utf-8")
    app = create_app(tick=False, ui_dir=tmp_path, addon_dirs=[])
    with TestClient(app) as c:
        assert c.get("/app.css").status_code == 200       # una página vieja en caché que pide /app.css
        assert c.get("/index.html").status_code == 200


def test_header_keeps_the_hexagonal_isotype_and_no_owner_name():
    html = (REPO / "ui" / "src" / "index.html").read_text(encoding="utf-8")
    assert 'id="jl-iso"' in html and '<use href="#jl-iso"' in html        # el hexágono es el símbolo de LeonRadio
    assert "image/svg+xml" in html                                         # y también el favicon
    assert "Jonathan" not in html                                          # el nombre del titular no aparece
