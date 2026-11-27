"""S6: seguridad de la API. Todo con carpetas temporales: nunca la base ni el config.json reales."""

import json
from contextlib import contextmanager
import os
import re
import socket
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from leonradio_core import auth, builtin, cli, paths, sdk, server, settings
from leonradio_core.server import create_app

KEY_RE = re.compile(r"[A-Z2-7]{4}(?:-[A-Z2-7]{4}){3}")
LAN = ("192.168.1.50", 40000)


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Ajustes y base en carpetas temporales (la carpeta de ajustes es `tmp/ajustes`, zona prohibida)."""
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "ajustes" / "config.json"))
    monkeypatch.setenv("LEONRADIO_DB", str(tmp_path / "ajustes" / "leonradio.db"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    (tmp_path / "home" / "Music").mkdir(parents=True)
    (tmp_path / "otra").mkdir()
    return tmp_path


def wav(path: Path, seconds: float = 0.2, rate: int = 22050) -> Path:
    t = np.arange(int(rate * seconds)) / rate
    pcm = (0.4 * 32767 * np.sin(2 * np.pi * 330 * t)).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(pcm.tobytes())
    return path


def make(cfg, **kw):
    app = create_app(tick=False, ui_dir=Path("/nonexistent"), addon_dirs=[], **kw)
    app.state.host.home = cfg / "home"
    return app


@pytest.fixture
def red(cfg):
    """Servidor en modo red con clave; el cliente es un equipo de la LAN (no loopback)."""
    key = auth.ensure_key()
    app = make(cfg, require_auth=True)
    with TestClient(app, client=LAN) as c:
        yield c, key, app


@contextmanager
def side(app, **kw):
    """Otro cliente sobre la misma app, sin repetir el ciclo de vida (que cerraría la base)."""
    yield TestClient(app, **kw)


def login(c, key):
    r = c.post("/api/login", json={"key": key})
    assert r.status_code == 200, r.text
    return r


def cmd(c, name, **args):
    return c.post(f"/api/commands/{name}", json={"args": args})


# --- modos -------------------------------------------------------------------
def test_local_sin_clave_funciona(cfg):
    with TestClient(make(cfg)) as c:
        assert c.get("/api/info").status_code == 200
        assert cmd(c, "explorer.mode", mode="lib").status_code == 200
        with c.websocket_connect("/ws"):
            pass
        assert c.get("/api/session").json()["auth_required"] is False


@pytest.mark.parametrize("method,url", [
    ("get", "/api/info"), ("get", "/api/audio"), ("get", "/api/editors"), ("get", "/api/editors/x/draw"),
    ("get", "/api/cover/1"), ("post", "/api/commands/playout.next")])
def test_red_sin_cookie_rechaza_todo(red, method, url):
    c, _key, _app = red
    assert getattr(c, method)(url).status_code == 401
    for doc in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(doc).status_code == 404
    s = c.get("/api/session")
    assert s.status_code == 200 and s.json()["auth_required"] and not s.json()["authenticated"]
    assert s.headers["cache-control"] == "no-store"


def test_red_no_arranca_sin_clave(cfg):
    with pytest.raises(RuntimeError, match="clave"):
        create_app(require_auth=True, addon_dirs=[], ui_dir=Path("/nonexistent"))


def test_serve_genera_y_muestra_clave_una_vez(cfg, monkeypatch, capsys):
    import uvicorn

    calls = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append(kw))
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server.serve(None, port, "null", host="0.0.0.0")
    first = capsys.readouterr().out
    key = KEY_RE.search(first)
    assert key and "CLAVE DE ACCESO" in first
    server.serve(None, port, "null", host="0.0.0.0")
    second = capsys.readouterr().out
    assert not KEY_RE.search(second) and "CLAVE DE ACCESO" not in second
    assert calls[0]["ws_max_size"] == 65536 and calls[0]["proxy_headers"] is False
    server.serve(None, port, "null")                      # modo local: no crea ni pide clave
    assert not KEY_RE.search(capsys.readouterr().out)


# --- clave y sesión ------------------------------------------------------------
def test_clave_se_guarda_como_hash(cfg):
    key = auth.ensure_key()
    raw = settings.path().read_text(encoding="utf-8")
    assert "scrypt$" in raw and key not in raw and key.replace("-", "") not in raw
    stored = settings.get_auth()["key_hash"]
    assert auth.verify(key.lower().replace("-", " "), stored) and auth.verify(key, stored)
    assert not auth.verify(auth.new_key(), stored)
    assert auth.ensure_key() is None


def test_login_ok_cookie_atributos(red):
    c, key, _app = red
    r = login(c, key)
    cookie = r.headers["set-cookie"]
    assert "leonradio_sesion=" in cookie and "HttpOnly" in cookie and "Max-Age=43200" in cookie
    assert "samesite=strict" in cookie.lower() and "Path=/" in cookie
    assert r.headers["cache-control"] == "no-store"
    assert c.get("/api/info").status_code == 200
    assert c.get("/api/session").json()["authenticated"] is True
    assert c.post("/api/logout").status_code == 200
    assert c.get("/api/info").status_code == 401


def test_login_clave_incorrecta(red):
    c, key, _app = red
    r = c.post("/api/login", json={"key": "AAAA-AAAA-AAAA-AAAA"})
    assert r.status_code == 401 and r.json() == {"detail": "Clave incorrecta"}
    assert "set-cookie" not in r.headers


def test_cambiar_clave_invalida_sesiones(red):
    c, key, _app = red
    login(c, key)
    assert c.get("/api/info").status_code == 200
    nueva = auth.rotate()                                  # lo que hace `leonradio clave`
    assert c.get("/api/info").status_code == 401
    assert c.post("/api/login", json={"key": key}).status_code == 401
    login(c, nueva)
    assert c.get("/api/info").status_code == 200


def test_bloqueo_por_intentos(red):
    c, key, app = red
    now = [1000.0]
    app.state.auth.guard.clock = lambda: now[0]
    mala = {"key": "AAAA-AAAA-AAAA-AAAA"}
    for _ in range(5):
        assert c.post("/api/login", json=mala).status_code == 401
    r = c.post("/api/login", json={"key": key})            # la 6.ª, aunque sea correcta
    assert r.status_code == 429 and int(r.headers["retry-after"]) > 0 and r.json()["retry_after"] > 0
    with side(app, client=("192.168.1.99", 1)) as otra:   # otra IP no se ve afectada
        assert otra.post("/api/login", json={"key": key}).status_code == 200
    now[0] += 15 * 60 + 1
    assert c.post("/api/login", json={"key": key}).status_code == 200
    for _ in range(4):                                     # un acierto antes del límite reinicia la cuenta
        c.post("/api/login", json=mala)
    assert c.post("/api/login", json={"key": key}).status_code == 200
    for _ in range(4):
        assert c.post("/api/login", json=mala).status_code == 401


# --- el propio PC entra sin clave aunque el servidor esté en modo red ------------
def test_pc_local_entra_sin_clave_en_modo_red(red):
    _c, _key, app = red
    for ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
        host = "[::1]:8765" if ip == "::1" else "127.0.0.1:8765"
        with side(app, base_url=f"http://{host}", client=(ip, 5000)) as pc:
            assert pc.get("/api/info").status_code == 200
            assert cmd(pc, "explorer.mode", mode="lib").status_code == 200
            with pc.websocket_connect("/ws", headers={"host": host}):      # el WS de pruebas no usa base_url para el Host
                pass
            s = pc.get("/api/session").json()
            assert s["auth_required"] is False and s["authenticated"] is True


def test_cliente_de_la_red_sin_sesion_es_rechazado(red):
    _c, _key, app = red
    for ip in ("192.168.1.50", "10.0.0.7", "8.8.8.8"):
        with side(app, base_url="http://127.0.0.1:8765", client=(ip, 5000)) as lan:   # miente en Host
            assert lan.get("/api/info").status_code == 401
            assert lan.get("/api/info", headers={"X-Forwarded-For": "127.0.0.1", "X-Real-IP": "127.0.0.1"}).status_code == 401
            with pytest.raises(WebSocketDisconnect):
                with lan.websocket_connect("/ws"):
                    pass
            assert lan.get("/api/session").json()["auth_required"] is True


def test_socket_loopback_con_host_ajeno_no_se_exime(red):
    """Un túnel o proxy local reenvía tráfico de fuera por loopback, pero con el Host de fuera."""
    _c, _key, app = red
    with side(app, base_url="http://radio.ejemplo.com", client=("127.0.0.1", 5000)) as pc:
        assert pc.get("/api/info").status_code == 401
        assert pc.get("/api/info", headers={"host": "192.168.1.5:8765"}).status_code == 401


def test_origin_se_comprueba_tambien_en_el_pc_local(red):
    _c, _key, app = red
    with side(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 5000)) as pc:
        assert pc.post("/api/commands/explorer.mode", json={"args": {"mode": "lib"}},
                       headers={"Origin": "http://evil.example"}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with pc.websocket_connect("/ws", headers={"origin": "http://evil.example"}):
                pass


# --- origen, host, tamaño ---------------------------------------------------------
def test_origin_ajeno_rechazado(cfg):
    with TestClient(make(cfg)) as c:
        url = "/api/commands/explorer.mode"
        body = {"args": {"mode": "disk"}}
        assert c.post(url, json=body, headers={"Origin": "http://evil.example"}).status_code == 403
        assert c.post(url, json=body, headers={"Origin": "null"}).status_code == 403
        assert c.app.state.host.state.get("explorer.mode") is None
        assert c.post(url, json=body, headers={"Origin": "http://testserver"}).status_code == 200
        assert c.post(url, json={"args": {"mode": "lib"}}).status_code == 200            # sin Origin: curl, scripts
        assert c.get("/api/info", headers={"Origin": "http://evil.example"}).status_code == 200


def test_login_con_origin_ajeno_403(red):
    c, key, _app = red
    assert c.post("/api/login", json={"key": key}, headers={"Origin": "http://evil.example"}).status_code == 403
    assert c.post("/api/login", json={"key": key}, headers={"Origin": "http://testserver"}).status_code == 200


def test_websocket_origin_ajeno(cfg):
    with TestClient(make(cfg)) as c:
        for url in ("/ws", "/ws/monitor"):
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect(url, headers={"origin": "http://evil.example"}):
                    pass
            with c.websocket_connect(url, headers={"origin": "http://testserver"}):
                pass


def test_websocket_sin_sesion_en_red(red):
    c, key, _app = red
    for url in ("/ws", "/ws/monitor"):
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect(url):
                pass
    r = login(c, key)
    cookie = {"cookie": f"leonradio_sesion={r.cookies['leonradio_sesion']}"}
    with c.websocket_connect("/ws/monitor", headers=cookie) as ws:
        assert ws.receive_json()["channels"] == 2
    with c.websocket_connect("/ws", headers=cookie):
        pass


def test_host_rebinding_en_loopback(cfg):
    with TestClient(make(cfg, strict_host=True)) as c:
        assert c.get("/api/info", headers={"host": "evil.example"}).status_code == 421
        assert c.get("/api/info", headers={"host": "127.0.0.1.evil.example"}).status_code == 421
        for ok in ("localhost", "localhost:8765", "127.0.0.1:8765", "[::1]:8765"):
            assert c.get("/api/info", headers={"host": ok}).status_code == 200, ok


def test_cuerpo_grande_413(cfg):
    with TestClient(make(cfg)) as c:
        headers = {"content-type": "application/json"}
        assert c.post("/api/commands/x", content=b"a" * 300 * 1024, headers=headers).status_code == 413

        def chunks():
            for _ in range(300):
                yield b"a" * 1024
        assert c.post("/api/commands/x", content=chunks(), headers=headers).status_code == 413    # sin Content-Length
        small = c.post("/api/commands/explorer.group", json={"args": {"key": "a" * 1000}})
        assert small.status_code == 200
        assert small.headers["x-content-type-options"] == "nosniff" and small.headers["x-frame-options"] == "DENY"


def test_ws_mensaje_grande_cierra(cfg):
    with TestClient(make(cfg)) as c:
        with c.websocket_connect("/ws") as ws:
            ws.send_text("a" * 70000)
            with pytest.raises(WebSocketDisconnect):
                ws.receive_text()


# --- rutas permitidas ---------------------------------------------------------------
def test_ruta_fuera_de_lista_rechazada(cfg):
    otra = cfg / "otra"
    wav(otra / "x.wav")
    with TestClient(make(cfg)) as c:
        for name, args in (("explorer.cd", {"path": str(otra)}), ("list.add_path", {"path": str(otra / "x.wav")}),
                           ("explorer.add_folder", {"path": str(otra)}),
                           ("stream.set", {"record_dir": str(otra / "rec")})):
            r = cmd(c, name, **args)
            assert r.status_code == 400, name
            assert str(cfg) not in r.text and "otra" not in r.text, name
            assert "permitidas" in r.json()["detail"]


def test_ruta_dentro_de_lista_ok(cfg):
    music = cfg / "home" / "Music"
    (music / "sub").mkdir()
    wav(music / "sub" / "Tema - Autor.wav")
    with TestClient(make(cfg)) as c:
        assert cmd(c, "explorer.cd", path=str(music)).status_code == 200
        assert cmd(c, "explorer.cd", path=str(music / "sub")).status_code == 200
        assert cmd(c, "list.add_path", path=str(music / "sub" / "Tema - Autor.wav")).status_code == 200
        assert cmd(c, "explorer.add_folder", path=str(music / "sub")).status_code == 200
        assert cmd(c, "stream.set", record_dir=str(music / "grabaciones")).status_code == 200
        assert settings.load()["stream"]["record_dir"] == str((music / "grabaciones").resolve())


def test_ruta_punto_punto(cfg):
    music = cfg / "home" / "Music"
    (music / "sub").mkdir()
    with TestClient(make(cfg)) as c:
        for p in (f"{music}{os.sep}..{os.sep}..{os.sep}otra", f"{music}{os.sep}sub{os.sep}..{os.sep}..{os.sep}..{os.sep}otra"):
            assert cmd(c, "explorer.cd", path=p).status_code == 400
        assert cmd(c, "explorer.cd", path=f"{music}{os.sep}sub{os.sep}..").status_code == 200   # vuelve a Music: permitido


def test_ruta_unc(cfg, monkeypatch):
    music = cfg / "home" / "Music"
    for unc in ("\\\\servidor\\share\\x", "//servidor/share", "\\\\?\\C:\\Windows", "\\\\.\\C:\\"):
        with TestClient(make(cfg)) as c:
            assert cmd(c, "explorer.cd", path=unc).status_code == 400
    def no_resolver(self, *a, **k):
        raise AssertionError("no se debe resolver una ruta UNC")
    monkeypatch.setattr(Path, "resolve", no_resolver)
    for unc in ("\\\\servidor\\share\\x", "//servidor/share", "\\\\?\\C:\\Windows"):
        with pytest.raises(ValueError, match="permitidas"):
            paths.check(unc, [music])


def test_ruta_enlace_simbolico(cfg, monkeypatch):
    music, otra = cfg / "home" / "Music", cfg / "otra"
    link = music / "enlace"
    try:
        os.symlink(otra, link, target_is_directory=True)
    except (OSError, NotImplementedError):                 # Windows sin permiso para crear enlaces: se simula
        orig = Path.resolve

        def fake(self, strict=False):
            return orig(otra) if self.name == "enlace" else orig(self, strict=strict)
        monkeypatch.setattr(Path, "resolve", fake)
    with pytest.raises(ValueError, match="permitidas"):
        paths.check(str(link), [music], must="dir")


def test_carpeta_de_ajustes_prohibida(cfg):
    ajustes = settings.path().parent
    settings.set_allowed_paths([str(ajustes.parent)])      # un padre de la carpeta de ajustes es permitido…
    with TestClient(make(cfg)) as c:
        assert cmd(c, "explorer.cd", path=str(cfg / "otra")).status_code == 200
        assert cmd(c, "explorer.cd", path=str(ajustes)).status_code == 400          # …pero no los ajustes
        assert cmd(c, "list.add_path", path=str(settings.path())).status_code == 400
    with pytest.raises(ValueError, match="ajustes"):
        paths.validate_new_root(str(ajustes.parent))


def test_load_m3u_solo_biblioteca_y_extension(cfg):
    lib = cfg / "lib"
    lib.mkdir()
    (lib / "notas.txt").write_text("x", encoding="utf-8")
    (lib / "lista.m3u").write_text("#EXTM3U\nTema.wav\n", encoding="utf-8")
    (cfg / "otra" / "lista.m3u").write_text("#EXTM3U\n", encoding="utf-8")
    (cfg / "home" / "Music" / "lista.m3u").write_text("#EXTM3U\n", encoding="utf-8")
    with TestClient(make(cfg, library_dir=str(lib))) as c:
        assert cmd(c, "list.load_m3u", path=str(lib / "notas.txt")).status_code == 400
        assert cmd(c, "list.load_m3u", path=str(cfg / "otra" / "lista.m3u")).status_code == 400
        assert cmd(c, "list.load_m3u", path=str(cfg / "home" / "Music" / "lista.m3u")).status_code == 400   # permitida, pero no es la biblioteca
        assert cmd(c, "list.load_m3u", path=str(lib / "lista.m3u")).status_code == 200


def test_explorador_muestra_solo_lugares_permitidos(cfg):
    music = cfg / "home" / "Music"
    app = make(cfg)
    host = app.state.host
    host.run_command("explorer.mode", {"mode": "disk"})
    tree = host.draw_editor("explorador")
    buttons = [n.get("label") for n in _all(tree) if n["t"] == "button"]
    assert "Música" in buttons and "Inicio" not in buttons and not any(b and re.fullmatch(r"[A-Z]:", b) for b in buttons)
    host.set_state("explorer.path", str(cfg / "otra"))     # estado viejo fuera de la lista: vuelve a la primera
    shown = [n.get("text") for n in _all(host.draw_editor("explorador")) if n["t"] == "label"]
    assert str(music.resolve()) in shown and str(cfg / "otra") not in shown


def _all(node):
    yield node
    for c in node.get("children", []):
        yield from _all(c)
    for t in node.get("tabs", []):
        yield from _all(t)


def test_carpetas_cli(cfg, capsys):
    d = cfg / "externo"
    d.mkdir()
    cli.main(["carpetas", "--agregar", str(d)])
    assert settings.get_allowed_paths() == [str(d.resolve())]
    cli.main(["carpetas", "--lista"])
    assert "Música" in capsys.readouterr().out
    for bad in (str(cfg / "no-existe"), "\\\\servidor\\share", Path(cfg.anchor).as_posix(), str(settings.path().parent)):
        with pytest.raises(SystemExit):
            cli.main(["carpetas", "--agregar", bad])
    assert settings.get_allowed_paths() == [str(d.resolve())]
    cli.main(["carpetas", "--quitar", str(d)])
    assert settings.get_allowed_paths() == []
    with pytest.raises(SystemExit):
        cli.main(["carpetas", "--quitar", str(d)])


def test_cli_clave_crea_una_nueva(cfg, capsys):
    cli.main(["clave"])
    k1 = KEY_RE.search(capsys.readouterr().out).group(0)
    cli.main(["clave"])
    k2 = KEY_RE.search(capsys.readouterr().out).group(0)
    h = settings.get_auth()["key_hash"]
    assert k1 != k2 and auth.verify(k2, h) and not auth.verify(k1, h)


# --- errores, logs, riesgo ----------------------------------------------------------
def test_error_500_sin_traza(cfg):
    app = make(cfg)
    app.state.host.register_command("x.boom", lambda ctx: 1 / 0)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.post("/api/commands/x.boom")
    assert r.status_code == 500 and r.json() == {"detail": "Error interno"}
    assert "Traceback" not in r.text and "ZeroDivision" not in r.text


def test_oserror_sin_ruta(cfg):
    def boom(ctx):
        raise FileNotFoundError(2, "El sistema no puede encontrar el archivo", "C:\\secreto\\x.wav")

    app = make(cfg)
    app.state.host.register_command("x.oserror", boom)
    with TestClient(app) as c:
        r = c.post("/api/commands/x.oserror")
        assert r.status_code == 400 and r.json()["detail"] == "El sistema no puede encontrar el archivo"
        assert "secreto" not in r.text


def test_logs_sin_secretos(red, caplog):
    c, key, app = red
    caplog.set_level("INFO")
    c.post("/api/login", json={"key": "AAAA-AAAA-AAAA-AAAA"})
    r = login(c, key)
    token = r.cookies["leonradio_sesion"]
    cmd(c, "stream.set", password="HackMe123", host="x.example")
    cmd(c, "explorer.cd", path=str(app.state.host.home))                                 # rechazo: se registra sin argumentos
    cmd(c, "explorer.mode", mode="lib")
    text = caplog.text
    for secret in (key, key.replace("-", ""), settings.get_auth()["key_hash"], token, "HackMe123"):
        assert secret not in text


def test_api_no_devuelve_password_icecast(cfg):
    with TestClient(make(cfg)) as c:
        assert cmd(c, "stream.set", password="HackMe123", host="x.example").status_code == 200
        assert "HackMe123" not in c.get("/api/editors/streaming/draw").text
        assert "HackMe123" not in c.get("/api/info").text
        assert "HackMe123" not in json.dumps(c.app.state.host.state, default=str)


def test_todo_comando_tiene_riesgo():
    host = sdk.Host()
    builtin.register(host).stop()
    names = {n for n, (_f, owner, _p) in host.commands.items() if owner == "builtin"}
    assert names <= set(builtin.RISK)
    for n in names:
        assert host.command_risk[n] == builtin.RISK[n]
    assert host.command_risk["stream.set"] == "config"
    for n in ("audio.set_route", "audio.set_input", "audio.test"):
        assert host.command_risk[n] == "config"
    for n in ("explorer.cd", "list.add_path", "explorer.add_folder", "list.load_m3u"):
        assert host.command_risk[n] == "archivos"
    with pytest.raises(ValueError):
        host.register_command("x.y", lambda ctx: None, risk="inventado")


def test_pruebas_no_tocan_config_real(cfg):
    key = auth.ensure_key()
    with TestClient(make(cfg, require_auth=True), client=LAN) as c:
        login(c, key)
        cmd(c, "stream.set", host="x.example")
    assert settings.path().is_file()
    assert not (cfg / "localappdata" / "LeonRadio").exists()


# --- ronda de correcciones -----------------------------------------------------------
@pytest.mark.parametrize("unc", [r"/\10.255.255.1\s\x", r"\/host/share", "//host/share", r"\\host\share",
                                 r"\\?\C:\Windows", r"C:\Users\x:ads"])
def test_unc_mixta_y_ads_rechazadas_sin_tocar_la_red(cfg, unc):
    import time

    music = cfg / "home" / "Music"
    t0 = time.monotonic()
    with pytest.raises(ValueError, match="permitidas"):
        paths.check(unc, [music])
    with pytest.raises(ValueError, match="permitidas"):
        paths.check(unc, [music], must="dir", create_ok=True)
    with pytest.raises(ValueError):
        paths.validate_new_root(unc)
    assert time.monotonic() - t0 < 1


def test_ads_en_carpeta_nueva_rechazada(cfg):
    music = cfg / "home" / "Music"
    if os.name == "nt":
        with pytest.raises(ValueError, match="permitidas"):
            paths.check(str(music / "nuevo:ads"), [music], create_ok=True)


def test_ajustes_ilegibles_no_se_pisan(cfg):
    settings.save({"stream": {"password": "HackMe123"}})
    settings.path().write_text("{ esto no es json", encoding="utf-8")
    assert settings.load() == {}
    with pytest.raises(settings.SettingsError):
        settings.load(strict=True)
    with pytest.raises(settings.SettingsError):
        settings.set_auth_hash("x")
    with pytest.raises(settings.SettingsError):
        settings.set_allowed_paths(["x"])
    assert settings.path().read_text(encoding="utf-8") == "{ esto no es json"       # intacto


def test_base_elegida_con_db_tambien_esta_protegida(cfg):
    otra_db = cfg / "home" / "Music" / "datos"
    otra_db.mkdir()
    db = otra_db / "mi.db"
    db.write_bytes(b"x")
    paths.protect(str(db))
    with pytest.raises(ValueError, match="permitidas"):
        paths.check(str(db), [cfg / "home" / "Music"], must="file")
    with pytest.raises(ValueError, match="permitidas"):
        paths.check(str(otra_db / "mi.db-wal"), [cfg / "home" / "Music"], create_ok=True)
    paths._protected_dbs.clear()


def test_loginguard_no_desaloja_bloqueos_vigentes():
    g = auth.LoginGuard(clock=lambda: 100.0)
    for _ in range(auth.MAX_FAILS):
        g.fail("victima")
    for i in range(auth.MAX_TRACKED_IPS + 50):
        g.fail(f"10.0.{i // 250}.{i % 250}")
    assert g.wait("victima") > 0


def test_add_folder_ignora_enlaces_hacia_fuera(cfg):
    music, otra = cfg / "home" / "Music", cfg / "otra"
    wav(otra / "fuera.wav"); wav(music / "dentro.wav")
    try:
        os.symlink(otra / "fuera.wav", music / "enlace.wav")
    except (OSError, NotImplementedError):
        pytest.skip("Windows sin permiso para crear enlaces")
    app = make(cfg)
    r = app.state.host.run_command("explorer.add_folder", {"path": str(music)})
    assert r == {"added": 1}


def test_lugares_sin_repetidos(cfg):
    (cfg / "home" / "Desktop").mkdir()
    (cfg / "home" / "OneDrive" / "Desktop").mkdir(parents=True)
    names = [n for n, _p in paths.places(None, cfg / "home")]
    assert len(names) == len({str(p).lower() for _n, p in paths.places(None, cfg / "home")})
    assert names.count("Escritorio") == 1 and "Escritorio (OneDrive)" in names
    settings.set_allowed_paths([str(cfg / "home" / "Music")])           # una ya permitida no se repite
    assert len(paths.places(None, cfg / "home")) == len(names)


def test_session_devuelve_retry_after_si_hay_bloqueo(red):
    c, key, app = red
    for _ in range(5):
        c.post("/api/login", json={"key": "AAAA-AAAA-AAAA-AAAA"})
    s = c.get("/api/session").json()
    assert s["retry_after"] > 0 and s["authenticated"] is False


def test_conectar_qr_un_solo_uso(tmp_path, monkeypatch):
    """El QR del PC lleva un enlace de un solo uso que da sesión al teléfono; el teléfono no puede pedir el QR."""
    from fastapi.testclient import TestClient
    from leonradio_core import auth
    from leonradio_core.server import create_app
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    auth.rotate()
    app = create_app(library_dir=None, db_path=str(tmp_path / "t.db"), audio="null", require_auth=True)
    app.state.auth.pairing.clock = lambda: 0.0
    pc = TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 5000))
    phone = TestClient(app, base_url="http://192.168.1.5:8765", client=("192.168.1.5", 5000))
    assert phone.get("/conectar").status_code == 403
    token = app.state.auth.pairing.create()
    assert phone.get("/api/info").status_code == 401
    r = phone.get(f"/p/{token}", follow_redirects=False)
    assert r.status_code == 303 and phone.get("/api/info").status_code == 200
    other = TestClient(app, base_url="http://192.168.1.6:8765", client=("192.168.1.6", 5000))
    assert other.get(f"/p/{token}", follow_redirects=False).status_code == 404     # ya usado
    assert other.get("/p/inventado", follow_redirects=False).status_code == 404
    assert pc.get("/conectar").status_code == 200


def test_conectar_rechaza_peticion_cruzada(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from leonradio_core import auth
    from leonradio_core.server import create_app
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    auth.rotate()
    app = create_app(library_dir=None, db_path=str(tmp_path / "t.db"), audio="null", require_auth=True)
    pc = TestClient(app, base_url="http://127.0.0.1:8765", client=("127.0.0.1", 5000))
    assert pc.get("/conectar", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert pc.get("/conectar", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
