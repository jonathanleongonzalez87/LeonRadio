"""S8a: marco de entidades compartidas. Todo con `:memory:` o carpetas temporales, datos inventados."""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leonradio_core import auth, db, entities, estaciones, sdk
from leonradio_core.entities import Entity, Field
from leonradio_core.server import create_app

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "core" / "src" / "leonradio_core"
LAN = ("192.168.1.50", 40000)

SALA = Entity("sala", "sala", owner="produccion", label="Sala de grabación", about="Espacio donde se graba",
              fields=(Field("nombre", required=True), Field("nombre_norm", derived_from="nombre", unique=True),
                      Field("capacidad", "int"), Field("estado", choices=("libre", "ocupada")),
                      Field("notas", max_len=20)))
SALA_SQL = """CREATE TABLE sala (id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL, nombre_norm TEXT NOT NULL UNIQUE, capacidad INTEGER, estado TEXT, notas TEXT,
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL)"""
EQUIPO = Entity("equipo", "equipo", owner="produccion", label="Equipo", about="Aparato de la sala",
                fields=(Field("nombre", required=True), Field("sala_id", "int", ref="sala")))
EQUIPO_SQL = """CREATE TABLE equipo (id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, sala_id INTEGER REFERENCES sala(id),
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0,1)),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_by TEXT NOT NULL)"""


@pytest.fixture
def host():
    h = sdk.Host(":memory:")
    estaciones.register_all(h)
    h.db.execute(SALA_SQL)
    h.db.execute(EQUIPO_SQL)
    h.entities.declare(SALA)
    h.entities.declare(EQUIPO)
    h.entities.validate()
    return h


def test_declarar_rechaza_duplicados_y_nombres_malos(host):
    reg = host.entities
    with pytest.raises(ValueError, match="ya está declarada"):
        reg.declare(SALA)
    with pytest.raises(ValueError, match="ya está declarada"):
        reg.declare(Entity("sala2", "sala", "produccion", "X", "x", (Field("nombre"),)))     # tabla repetida
    with pytest.raises(ValueError, match="identificador"):
        reg.declare(Entity("Sala X", "sala_x", "produccion", "X", "x", (Field("nombre"),)))
    with pytest.raises(ValueError, match="identificador"):
        reg.declare(Entity("ok", "ok; DROP", "produccion", "X", "x", (Field("nombre"),)))
    with pytest.raises(ValueError, match="identificador"):
        reg.declare(Entity("ok", "ok", "produccion", "X", "x", (Field("nombre; --"),)))
    with pytest.raises(ValueError, match="no es una estación"):
        reg.declare(Entity("ok", "ok", "marte", "X", "x", (Field("nombre"),)))
    reg.declare(Entity("huerfana", "huerfana", "produccion", "H", "h", (Field("nombre"), Field("x_id", "int", ref="nada"))))
    with pytest.raises(ValueError, match="no está declarada"):
        reg.validate()


def test_dueno_ajeno_no_escribe(host):
    with pytest.raises(sdk.PermissionDenied):
        host.entities.writer("direccion").create("artista", {"nombre": "Artista Uno"}, who="local")
    aid = host.entities.writer("programacion").create("artista", {"nombre": "Artista Uno"}, who="local")
    assert host.entities.get("artista", aid)["nombre"] == "Artista Uno"
    with pytest.raises(ValueError, match="el sistema"):          # pieza es anterior al marco: solo lectura
        host.entities.writer("programacion").create("pieza", {"title": "X"}, who="local")
    assert not hasattr(host.entities, "create") and not hasattr(sdk.Context, "create")


def test_marcas_y_principal(host):
    w = host.entities.writer("produccion")
    sid = w.create("sala", {"nombre": "Sala Uno"}, who="local")
    a = host.entities.get("sala", sid)
    assert a["created_by"] == a["updated_by"] == "local" and a["created_at"] == a["updated_at"]
    assert a["created_at"].endswith("+00:00") and a["nombre_norm"] == "sala uno"
    time.sleep(0.01)
    w.update("sala", sid, {"nombre": "Sala  UNO Bis"}, who="clave")
    b = host.entities.get("sala", sid)
    assert (b["created_by"], b["updated_by"], b["created_at"]) == ("local", "clave", a["created_at"])
    assert b["updated_at"] > a["updated_at"] and b["nombre_norm"] == "sala uno bis"


def test_archivar_no_borra(host):
    w = host.entities.writer("produccion")
    sid = w.create("sala", {"nombre": "Sala Uno"}, who="local")
    w.archive("sala", sid, who="local")
    assert host.entities.list("sala")["total"] == 0
    assert host.entities.list("sala", include_archived=True)["total"] == 1
    assert host.db.execute("SELECT COUNT(*) FROM sala").fetchone()[0] == 1
    w.restore("sala", sid, who="local")
    assert host.entities.list("sala")["total"] == 1
    with pytest.raises(ValueError, match="no existe"):
        w.archive("sala", 999, who="local")


def test_ref_valida_y_no_archivada(host):
    w = host.entities.writer("produccion")
    sid = w.create("sala", {"nombre": "Sala Uno"}, who="local")
    w.create("equipo", {"nombre": "Micrófono", "sala_id": sid}, who="local")
    with pytest.raises(ValueError, match="sala_id"):
        w.create("equipo", {"nombre": "X", "sala_id": 999}, who="local")
    w.archive("sala", sid, who="local")
    with pytest.raises(ValueError, match="sala_id"):
        w.create("equipo", {"nombre": "Y", "sala_id": sid}, who="local")
    with pytest.raises(sqlite3_errors()):                        # el motor también lo impide (foreign_keys=ON)
        host.db.execute("INSERT INTO equipo (nombre, sala_id, created_at, updated_at, created_by, updated_by) "
                        "VALUES ('Z', 12345, 'a', 'a', 'x', 'x')")


def sqlite3_errors():
    import sqlite3
    return sqlite3.IntegrityError


def test_choices_required_max_len(host):
    w = host.entities.writer("produccion")
    with pytest.raises(ValueError, match="falta"):
        w.create("sala", {"capacidad": 3}, who="local")
    with pytest.raises(ValueError, match="falta"):
        w.create("sala", {"nombre": "   "}, who="local")
    with pytest.raises(ValueError, match="debe ser uno de"):
        w.create("sala", {"nombre": "A", "estado": "rota"}, who="local")
    with pytest.raises(ValueError, match="admite hasta"):
        w.create("sala", {"nombre": "A", "notas": "x" * 21}, who="local")
    with pytest.raises(ValueError, match="no es un valor válido"):
        w.create("sala", {"nombre": "A", "capacidad": "muchas"}, who="local")
    with pytest.raises(ValueError, match="no tiene el campo"):
        w.create("sala", {"nombre": "A", "secreto": 1}, who="local")
    with pytest.raises(ValueError, match="no tiene el campo"):
        w.create("sala", {"nombre": "A", "nombre_norm": "forzado"}, who="local")      # derivado: lo calcula el servicio
    with pytest.raises(ValueError, match="no tiene el campo"):
        w.create("sala", {"nombre": "A", "archived": 1}, who="local")
    assert host.db.execute("SELECT COUNT(*) FROM sala").fetchone()[0] == 0


def test_where_solo_campos_declarados(host):
    w = host.entities.writer("produccion")
    a = w.create("sala", {"nombre": "Sala Uno", "estado": "libre"}, who="local")
    w.create("sala", {"nombre": "Sala Dos", "estado": "ocupada"}, who="local")
    assert [r["id"] for r in host.entities.list("sala", where={"estado": "libre"})["items"]] == [a]
    with pytest.raises(ValueError):
        host.entities.list("sala", where={"id; DROP TABLE sala": 1})
    with pytest.raises(ValueError):
        host.entities.list("sala", where={"created_by": "local"})        # columna estándar no declarada
    with pytest.raises(ValueError, match="entidad desconocida"):
        host.entities.list("no_existe")
    assert host.db.execute("SELECT COUNT(*) FROM sala").fetchone()[0] == 2


def test_paginacion_y_limite(host):
    host.db.executemany(
        "INSERT INTO sala (nombre, nombre_norm, created_at, updated_at, created_by, updated_by) VALUES (?,?,?,?,?,?)",
        [(f"Sala {i:05d}", f"sala {i:05d}", "t", "t", "x", "x") for i in range(5000)])
    t0 = time.perf_counter()
    page = host.entities.list("sala", limit=50, offset=4950)
    assert time.perf_counter() - t0 < 0.1
    assert page["total"] == 5000 and len(page["items"]) == 50 and page["items"][0]["nombre"] == "Sala 04950"
    assert host.entities.list("sala", limit=999999)["limit"] == 200
    assert host.entities.list("sala", offset=-5)["offset"] == 0


def test_unico_se_traduce_a_valueerror(host):
    w = host.entities.writer("produccion")
    w.create("sala", {"nombre": "Sala Uno"}, who="local")
    with pytest.raises(ValueError) as exc:
        w.create("sala", {"nombre": "  SALA   uno "}, who="local")
    assert str(exc.value) == "ya existe un registro igual"


def test_transaccion_hace_rollback_y_emite_una_vez(host):
    w = host.entities.writer("produccion")
    events = []
    host.events.subscribe(lambda n, d: events.append((n, d)) if n == "entities.changed" else None)
    with pytest.raises(RuntimeError):
        with host.entities.transaction():
            w.create("sala", {"nombre": "Sala Uno"}, who="local")
            raise RuntimeError("falla")
    assert host.db.execute("SELECT COUNT(*) FROM sala").fetchone()[0] == 0 and events == []
    with host.entities.transaction():
        for i in range(5):
            w.create("sala", {"nombre": f"Sala {i}"}, who="local")
        assert events == []
    assert len(events) == 1 and events[0][1]["entity"] == "sala"


def test_catalogo_de_entidades(host):
    cat = {c["nombre"]: c for c in host.entities.catalog()}
    assert {"pieza", "emision", "compromiso", "artista", "album", "genero", "sala"} <= set(cat)
    assert cat["compromiso"]["nota"] == "a rediseñar en A6" and cat["pieza"]["estado"] == "solo lectura"


# --- REST -------------------------------------------------------------------
@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "ajustes" / "config.json"))
    monkeypatch.setenv("LEONRADIO_DB", str(tmp_path / "ajustes" / "leonradio.db"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    return tmp_path


def make(cfg, **kw):
    return create_app(tick=False, ui_dir=Path("/nonexistent"), addon_dirs=[], **kw)


def seed(app):
    host = app.state.host
    host.db.execute("INSERT INTO assets (path, kind, title, artist) VALUES ('C:/secreto/x.wav','music','Tema Uno','Artista Uno')")
    host.db.execute("INSERT INTO assets (path, sha256, kind, title) VALUES ('C:/secreto/y.wav','abc123','music','Tema Dos')")
    host.db.commit()
    host.entities.writer("programacion").create("artista", {"nombre": "Artista Uno"}, who="local")


def test_rest_lectura(cfg):
    app = make(cfg)
    with TestClient(app) as c:
        seed(app)
        cat = c.get("/api/entities").json()
        assert {e["nombre"] for e in cat} >= {"pieza", "artista", "album", "genero", "emision", "compromiso"}
        r = c.get("/api/entities/pieza").json()
        assert r["total"] == 2 and r["limit"] == 50
        text = c.get("/api/entities/pieza").text + c.get("/api/entities/pieza/1").text
        assert "secreto" not in text and "abc123" not in text and '"path"' not in text and "sha256" not in text
        assert set(c.get("/api/entities/pieza/1").json()) == {"id", *(f.name for f in app.state.host.entities.get_entity("pieza").fields)}
        assert c.get("/api/entities/artista?limit=999999").json()["limit"] == 200
        assert c.get("/api/entities/artista?limit=abc").status_code == 422
        assert c.get("/api/entities/nada").status_code == 404
        assert c.get("/api/entities/artista/9999").status_code == 404
        assert c.get("/api/entities/artista/1").json()["nombre"] == "Artista Uno"


def test_rest_requiere_clave_en_modo_red(cfg):
    key = auth.ensure_key()
    app = make(cfg, require_auth=True)
    with TestClient(app, client=LAN) as c:
        for url in ("/api/entities", "/api/entities/artista", "/api/entities/artista/1"):
            assert c.get(url).status_code == 401
        assert c.post("/api/login", json={"key": key}).status_code == 200
        assert c.get("/api/entities").status_code == 200
        r = c.post("/api/commands/artista.crear", json={"args": {"nombre": "Artista Red"}})
        assert r.status_code == 200
        assert app.state.host.entities.get("artista", r.json()["result"])["created_by"] == "clave"


def test_comando_crear_firma_con_el_principal_y_errores_limpios(cfg):
    app = make(cfg)
    with TestClient(app) as c:
        r = c.post("/api/commands/artista.crear", json={"args": {"nombre": "Artista Uno"}})
        assert r.status_code == 200
        assert app.state.host.entities.get("artista", r.json()["result"])["created_by"] == "local"
        dup = c.post("/api/commands/artista.crear", json={"args": {"nombre": "artista uno"}})
        assert dup.status_code == 400 and dup.json()["detail"] == "ya existe un registro igual"
        bad = c.post("/api/commands/artista.crear", json={"args": {"id": 7, "nombre": "X"}})
        assert bad.status_code == 400 and "SQL" not in bad.text and "sqlite" not in bad.text.lower()
        assert c.post("/api/commands/artista.archivar", json={"args": {"id": r.json()["result"]}}).status_code == 200


def test_riesgo_de_comandos_de_entidades_es_datos(host):
    names = [n for n in host.commands if n.split(".")[0] in {"artista", "album", "genero"} or n == "catalogo.sincronizar"]
    assert len(names) == 13
    assert all(host.command_risk[n] == "datos" for n in names)


# --- panel ------------------------------------------------------------------
def _walk(node):
    yield node
    for ch in node.get("children", []):
        yield from _walk(ch)
    for tab in node.get("tabs", []):
        for ch in tab.get("children", []):
            yield from _walk(ch)


def test_panel_entidades_solo_lectura(host):
    editor, _o, _p = host.editors["entidades"]
    assert editor.station == ""
    tree = host.draw_editor("entidades")
    nodes = list(_walk(tree))
    assert not any(n["t"] in ("button", "form", "slider", "custom") for n in nodes)
    table = next(n for n in nodes if n["t"] == "table")
    assert table["columns"] == ["Entidad", "Qué es", "Dueño", "Activos", "Archivados", "Estado"]
    rows = {r[0]: r for r in table["rows"]}
    assert {"Pieza", "Registro de emisión", "Compromiso", "Artista", "Álbum", "Género"} <= set(rows)
    assert "a rediseñar en A6" in rows["Compromiso"][5] and rows["Artista"][2] == "Programación"
    assert "Jonathan" not in str(tree)


# --- importación, migraciones y docs ------------------------------------------
@pytest.mark.parametrize("mod", ["db", "sdk", "entities", "estaciones"])
def test_importar_en_cualquier_orden(mod):
    r = subprocess.run([sys.executable, "-I", "-c", f"import leonradio_core.{mod}"], cwd=REPO / "core",
                       capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(REPO / "core" / "src")})
    assert r.returncode == 0, r.stderr


def test_migraciones_nombre_y_orden():
    for i, fn in enumerate(db.MIGRATIONS):
        assert re.match(rf"^_?m{i + 1}_", fn.__name__), fn.__name__


def test_entidades_declaradas_estan_en_docs(host):
    docs = (REPO / "docs" / "entidades.md").read_text(encoding="utf-8")
    for e in host.entities.all():
        if e.name == "sala" or e.name == "equipo":               # ficticias de esta prueba
            continue
        assert f"`{e.table}`" in docs, f"falta `{e.table}` en docs/entidades.md"


def test_nadie_escribe_tablas_de_entidades_fuera_del_marco(host):
    tables = [e.table for e in host.entities.all() if e.managed and e.name not in ("sala", "equipo")]
    assert {"artista", "album", "genero"} <= set(tables)
    pat = re.compile(rf"\b(INSERT\s+(?:OR\s+\w+\s+)?INTO|UPDATE|DELETE\s+FROM)\s+({'|'.join(tables)})\b", re.I)
    for f in SRC.rglob("*.py"):
        if f.name in ("entities.py", "migraciones.py"):
            continue
        assert not pat.search(f.read_text(encoding="utf-8")), f"{f.name} escribe una tabla de entidad fuera del marco"


def test_no_existe_delete_en_el_servicio():
    for f in SRC.rglob("*.py"):
        assert not re.search(r"DELETE\s+FROM", f.read_text(encoding="utf-8"), re.I), f.name


def test_check_declaration_detecta_deriva(host):
    assert entities.check_declaration(host.db, SALA) == []
    assert entities.check_declaration(host.db, EQUIPO) == []
    otra = Entity("sala", "sala", "produccion", "S", "s", (*SALA.fields, Field("extra")))
    assert any("extra" in p for p in entities.check_declaration(host.db, otra))
    assert any("UNIQUE" in p for p in entities.check_declaration(
        host.db, Entity("equipo", "equipo", "produccion", "E", "e", (Field("nombre", unique=True),))))


def test_sala_del_contrato(host):
    """La misma prueba que lleva docs/entidades.md: el contrato está comprobado por el propio marco."""
    w = host.entities.writer("produccion")
    sid = w.create("sala", {"nombre": "Sala Uno", "capacidad": 4}, who="local")
    w.archive("sala", sid, who="local")
    assert host.entities.list("sala")["total"] == 0
    with pytest.raises(sdk.PermissionDenied):
        host.entities.writer("direccion").create("sala", {"nombre": "X"}, who="local")


def test_contexto_de_solo_lectura(host):
    ctx = sdk.Context(host, "addon", frozenset({"entities.read"}))
    assert ctx.entities.list("artista")["total"] == 0 and not hasattr(ctx.entities, "writer")
    with pytest.raises(sdk.PermissionDenied):
        sdk.Context(host, "addon", frozenset()).entities
    assert ctx.principal == "local" and sdk.Context(host, "x", frozenset(), "clave").principal == "clave"


def test_valores_raros_son_valueerror(host):
    w = host.entities.writer("produccion")
    sid = w.create("sala", {"nombre": "Sala Uno"}, who="local")
    grande = 2 ** 70
    for malo in (grande, True, {"a": 1}, [1], "1.5"):
        with pytest.raises(ValueError):
            host.entities.get("sala", malo)
        with pytest.raises(ValueError):
            w.update("sala", malo, {"nombre": "X"}, who="local")
        with pytest.raises(ValueError):
            w.archive("sala", malo, who="local")
    with pytest.raises(ValueError):
        w.create("sala", {"nombre": "A", "capacidad": grande}, who="local")
    with pytest.raises(ValueError):
        w.create("equipo", {"nombre": "A", "sala_id": grande}, who="local")
    with pytest.raises(ValueError):
        w.create("sala", {"nombre": "A", "capacidad": {"x": 1}}, who="local")
    with pytest.raises(ValueError, match="no válidos"):
        w.create("sala", {"nombre": "\ud800"}, who="local")
    with pytest.raises(ValueError):
        host.entities.list("sala", where={"capacidad": grande})
    with pytest.raises(ValueError):
        host.entities.list("sala", where={"nombre": "\ud800"})
    with pytest.raises(ValueError):
        host.entities.list("sala", where={"capacidad": [1]})
    assert host.entities.list("sala", offset=2 ** 80)["items"] == []
    assert host.entities.get("sala", sid)["nombre"] == "Sala Uno"


def test_rest_valores_raros_no_dan_500(cfg):
    app = make(cfg)
    with TestClient(app) as c:
        assert c.get(f"/api/entities/artista/{2 ** 70}").status_code == 404
        assert c.get(f"/api/entities/artista?limit={2 ** 70}&offset={2 ** 70}").status_code == 200
        for body in ('{"args": {"nombre": "\\ud800"}}', '{"args": {"nombre": "X", "notas": {"a": 1}}}'):
            r = c.post("/api/commands/artista.crear", content=body, headers={"Content-Type": "application/json"})
            assert r.status_code == 400, r.text
        for bad in (2 ** 70, {"a": 1}, [1]):
            assert c.post("/api/commands/artista.archivar", json={"args": {"id": bad}}).status_code == 400
        assert c.post("/api/commands/album.crear", json={"args": {"titulo": "T", "artista_id": 2 ** 70}}).status_code == 400


def test_register_crud_comprueba_el_dueno_al_registrar(host):
    with pytest.raises(ValueError, match="no es una entidad de direccion"):
        entities.register_crud(host, "direccion", ["sala"])
    assert "sala.crear" not in host.commands
    entities.register_crud(host, "produccion", ["sala"])
    assert host.command_risk["sala.crear"] == "datos"
