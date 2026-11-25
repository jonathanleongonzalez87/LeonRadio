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
    assert {"aire", "cola", "historial"} <= set(host.editors)
    tree = host.draw_editor("aire")
    kinds = [c["t"] for c in tree["children"]]
    assert "progress" in kinds
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
        assert {"aire", "cola", "historial", "ejemplo.hora"} <= eds
        assert c.get("/api/editors/aire/draw").json()["t"] == "column"
        assert c.post("/api/commands/ejemplo.pulsar").json()["result"] == 1
        assert c.post("/api/commands/ejemplo.pulsar").json()["result"] == 2
        assert c.post("/api/commands/no.existe").status_code == 404
        assert c.get("/api/editors/nada/draw").status_code == 404
        info = c.get("/api/info").json()
        assert info["addons"][0]["id"] == "com.leonradio.ejemplo-hora"


def test_vintage_editors_use_custom_components_and_cartwall_fires(tmp_path):
    lib = tmp_path / "Radio" / "Vestido General" / "Jingles"
    lib.mkdir(parents=True)
    (lib / "Jingle 1.wav").write_bytes(b"X")
    from leonradio_core import library
    host = sdk.Host()
    library.scan(host.db, tmp_path / "Radio")
    builtin.register(host)
    comps = {}
    for ed in ("vu", "reloj", "dial", "cartuchera"):
        tree = host.draw_editor(ed)
        custom = [c for c in tree["children"] if c["t"] == "custom"]
        assert len(custom) == 1, ed
        comps[ed] = custom[0]
    assert comps["vu"]["component"] == "vu-meter"
    assert comps["reloj"]["props"]["timezone"] == "America/Bogota"
    assert comps["dial"]["props"]["name"] == "RRC"
    pad = comps["cartuchera"]["props"]["pads"][0]
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


def test_compact_strip_editors_draw():
    host = sdk.Host()
    builtin.register(host)
    bar = host.draw_editor("aire-barra")
    tones = [c.get("tone") for c in bar["children"] if c["t"] == "label"]
    assert "title" in tones                       # título en una sola línea
    assert any(c["t"] == "row" and any(x["t"] == "progress" for x in c["children"]) for c in bar["children"])
    assert host.draw_editor("proxima")["children"][0]["text"] == "PRÓXIMA"
    hora = host.draw_editor("hora")["children"][0]
    assert hora["component"] == "digital-clock" and hora["props"]["timezone"] == "America/Bogota"
