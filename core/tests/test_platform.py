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
