import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leonradio_core import addons, builtin, sdk
from leonradio_core.server import create_app
from leonradio_core.uischema import UI

REPO = Path(__file__).resolve().parents[2]


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
    builtin.register(host)
    assert {"aire", "emision", "historial", "proxima", "botonera"} <= set(host.editors)
    tree = host.draw_editor("aire")
    def walk(n):
        yield n["t"]
        for c in n.get("children", []):
            yield from walk(c)
    assert "progress" in set(walk(tree))      # el progreso está (ahora junto a los botones, en una fila)
    host.run_command("playout.next")  # salta: queda registrado como 'skipped'
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
    (lib / "Jingle 1.wav").write_bytes(b"X")
    from leonradio_core import library
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    builtin.register(host)
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
    assert pad["key"] == "F1" and pad["style"] == "orange"
    host.run_command("cart.fire", {"asset_id": pad["asset_id"]})
    row = host.db.execute("SELECT source, title FROM playlog").fetchone()
    assert (row["source"], row["title"]) == ("cart", "Jingle 1")


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



def test_botonera_has_tabs_events_and_explorer(tmp_path):
    lib = tmp_path / "Radio" / "Música" / "20s"
    lib.mkdir(parents=True)
    (lib / "Brilla - Providencia.mp3").write_bytes(b"A")
    from leonradio_core import library
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    builtin.register(host)
    tabs = next(n for n in _walk(host.draw_editor("botonera")) if n["t"] == "tabs")
    assert [t["label"] for t in tabs["tabs"]] == ["Botonera", "Eventos", "Explorador"]
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
    (lib / "Brilla - Providencia.mp3").write_bytes(b"A")
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
    assert any(n["t"] == "progress" for n in _walk(tree))
    assert {"aux1", "aux2", "aux3", "aux4"} <= set(host.editors)
