"""A6a: clientes, contratos y compromisos de pauta (Producción). `:memory:` o carpetas temporales, datos inventados."""

import json
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leonradio_core import db, entities, estaciones, sdk
from leonradio_core.estaciones.produccion import comercial, entidades, migraciones
from leonradio_core.server import create_app

REPO = Path(__file__).resolve().parents[2]
PROD = REPO / "core" / "src" / "leonradio_core" / "estaciones" / "produccion"


@pytest.fixture
def host():
    h = sdk.Host(":memory:")
    estaciones.register_all(h)
    return h


def cuna(host, title="Cuña Prueba", kind="spot", status="active") -> int:
    cur = host.db.execute("INSERT INTO assets (path, kind, title, status) VALUES (?,?,?,?)",
                          (f"x/{title}-{kind}-{status}.wav", kind, title, status))
    host.db.commit()
    return cur.lastrowid


def run(host, name, **args):
    return host.run_command(name, args)


def base_comercial(host):
    """Cliente, contrato de diciembre y una cuña: lo mínimo para registrar pauta."""
    cli = run(host, "cliente.crear", nombre="Cliente Uno S.A.S.")
    con = run(host, "contrato.crear", codigo="rrc-2026-001", cliente_id=cli, tipo="patrocinio",
              desde="2026-12-01", hasta="2026-12-31", valor_cop="1.500.000")
    return cli, con, cuna(host)


PAUTA = dict(campana="Navidad", cantidad=60, desde="2026-12-01", hasta="2026-12-15",
             franja_desde="06:00", franja_hasta="10:00")


# --- migración -------------------------------------------------------------------------------------------------------
def base_v3(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    for fn in db.MIGRATIONS[:3]:
        fn(conn)
    conn.execute("PRAGMA user_version = 3")
    conn.execute("INSERT INTO assets (id, path, kind, title) VALUES (5, 'c.wav', 'spot', 'Cuña Vieja')")
    conn.execute("INSERT INTO commitments (id, client, campaign, contract_ref, asset_id, plays_required, window_start, "
                 "window_end, daypart_start, daypart_end, notes) VALUES "
                 "(10, 'Cliente Viejo', 'Campaña A', 'REF-1', 5, 30, '2026-11-01T00:00:00Z', '2026-12-01T00:00:00Z', "
                 "'06:00', '10:00', 'nota'), "
                 "(11, 'Cliente Viejo Dos', NULL, NULL, NULL, 5, '2026-11-02T00:00:00Z', '2026-11-03T00:00:00Z', "
                 "NULL, NULL, NULL)")
    for i, cid in enumerate((10, 10, 11)):
        conn.execute("INSERT INTO playlog (station, started_at, kind, title, commitment_id) VALUES "
                     "('RRC', ?, 'spot', 'Cuña Vieja', ?)", (f"2026-11-0{i + 2}T12:00:00Z", cid))
    conn.commit()
    return conn


V1_COLS = "id, client, campaign, contract_ref, asset_id, plays_required, window_start, window_end, daypart_start, daypart_end, notes"


def test_migracion4_desde_v3_conserva_commitments_y_playlog(tmp_path):
    base_v3(tmp_path / "v3.db").close()
    viejo = sqlite3.connect(str(tmp_path / "v3.db"))
    antes = viejo.execute(f"SELECT {V1_COLS} FROM commitments ORDER BY id").fetchall()
    antes_log = viejo.execute("SELECT id, commitment_id FROM playlog ORDER BY id").fetchall()
    viejo.close()
    conn = db.connect(tmp_path / "v3.db")
    assert db.version(conn) == len(db.MIGRATIONS) >= 4
    tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"cliente", "contrato"} <= tablas
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(commitments)")}
    assert {"contrato_id", "archived", "created_at", "updated_at", "created_by", "updated_by"} <= cols
    assert [tuple(r) for r in conn.execute(f"SELECT {V1_COLS} FROM commitments ORDER BY id")] == [tuple(r) for r in antes]
    for r in conn.execute("SELECT archived, created_by, updated_by, created_at, contrato_id FROM commitments"):
        assert (r["archived"], r["created_by"], r["updated_by"], r["contrato_id"]) == (0, "sistema", "sistema", None)
        assert r["created_at"]
    assert [tuple(r) for r in conn.execute("SELECT id, commitment_id FROM playlog ORDER BY id")] == [tuple(r) for r in antes_log]
    conn.close()


def test_migracion4_idempotente(tmp_path):
    conn = db.connect(tmp_path / "x.db")
    conn.execute("INSERT INTO commitments (client, plays_required, window_start, window_end) VALUES ('C', 1, 'a', 'b')")
    fotos = []
    for _ in range(2):
        migraciones.m4_comercial(conn)
        fotos.append((conn.execute("SELECT * FROM commitments").fetchall(),
                      conn.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()))
    assert [tuple(r) for r in fotos[0][0]] == [tuple(r) for r in fotos[1][0]]
    assert fotos[0][1] == fotos[1][1]
    conn.close()


def test_migracion_solo_agrega():
    for f in PROD.glob("*.py"):
        assert not re.search(r"DROP TABLE|RENAME|DELETE FROM", f.read_text(encoding="utf-8")), f.name


def test_check_declaration_produccion(host):
    for e in entidades.ALL:
        assert entities.check_declaration(host.db, e) == [], e.name
    assert host.entities.get_entity("compromiso").managed


# --- dueño y riesgo ----------------------------------------------------------------------------------------------------
def test_solo_produccion_escribe(host):
    cli, con, aid = base_comercial(host)
    otro = host.entities.writer("programacion")
    for name, values in (("cliente", {"nombre": "X"}), ("contrato", {"codigo": "X"}), ("compromiso", {"plays_required": 1})):
        with pytest.raises(sdk.PermissionDenied):
            otro.create(name, values, who="local")
    for station in ("programacion", "al_aire"):
        ctx = sdk.Context(host, station, frozenset({"entities.read"}))
        assert ctx.entities.list("cliente")["total"] == 1
        assert ctx.entities.list("contrato")["total"] == 1
        assert ctx.entities.list("compromiso")["total"] == 0


DATOS = [n for p in ("cliente", "contrato", "compromiso") for n in (f"{p}.crear", f"{p}.editar", f"{p}.archivar", f"{p}.restaurar")]
DATOS += ["produccion.campo", "produccion.guardar"]
NORMAL = ["produccion.ver", "produccion.cerrar", "produccion.archivados", "produccion.pagina"]


def test_riesgo_de_comandos_produccion(host):
    nuestros = [n for n in host.commands if n.split(".")[0] in ("cliente", "contrato", "compromiso", "produccion")]
    assert sorted(nuestros) == sorted(DATOS + NORMAL)
    assert all(host.command_risk[n] == "datos" for n in DATOS)
    assert all(host.command_risk[n] == "normal" for n in NORMAL)


# --- cliente ------------------------------------------------------------------------------------------------------------
def test_cliente_unico_y_sin_datos_de_contacto(host):
    cid = run(host, "cliente.crear", nombre="Cliente Uno S.A.S.")
    assert host.entities.get("cliente", cid)["nombre"] == "Cliente Uno S.A.S."
    with pytest.raises(ValueError) as exc:
        run(host, "cliente.crear", nombre="  cliente uno s.a.s. ")
    assert str(exc.value) == "ya existe un cliente con ese nombre"
    with pytest.raises(ValueError) as exc:
        run(host, "cliente.crear", nombre="")
    assert str(exc.value) == "falta «nombre»"
    cols = {r["name"] for r in host.db.execute("PRAGMA table_info(cliente)")}
    assert not any(re.search(r"tel|correo|mail|documento|nit|direcc", c) for c in cols), cols
    run(host, "cliente.editar", id=cid, nombre="Cliente Uno S.A.S")          # el mismo cliente puede renombrarse
    with pytest.raises(ValueError, match="no tiene el campo"):
        run(host, "cliente.crear", nombre="Otro", telefono="300")


# --- contrato ------------------------------------------------------------------------------------------------------------
def test_contrato_normaliza(host):
    cli, con, _aid = base_comercial(host)
    c = host.entities.get("contrato", con)
    assert (c["codigo"], c["valor_cop"], c["tipo"], c["cliente_id"]) == ("RRC-2026-001", 1500000, "patrocinio", cli)
    assert "Cliente Uno" not in json.dumps(c)


CONTRATO_OK = dict(codigo="RRC-2026-002", tipo="pauta", desde="2026-12-01", hasta="2026-12-31")


@pytest.mark.parametrize("cambio, mensaje", [
    ({"hasta": "2026-11-30"}, "«hasta» no puede ser anterior a «desde»"),
    ({"desde": "01/12/2026"}, "«desde» debe ser una fecha, por ejemplo 01/12/2026"),
    ({"hasta": "2026-02-30"}, "«hasta» debe ser una fecha, por ejemplo 01/12/2026"),
    ({"tipo": "canje"}, "el tipo debe ser «pauta» o «patrocinio»"),
    ({"valor_cop": -5}, "el valor debe ser un monto en pesos, por ejemplo 1.500.000"),
    ({"valor_cop": "-5"}, "el valor debe ser un monto en pesos, por ejemplo 1.500.000"),
    ({"valor_cop": "1500000,50"}, "el valor va en pesos, sin centavos"),
    ({"valor_cop": "mil pesos"}, "el valor debe ser un monto en pesos, por ejemplo 1.500.000"),
    ({"cliente_id": 999}, "elige un cliente activo"),
    ({"cliente_id": "archivado"}, "elige un cliente activo"),
    ({"codigo": " rrc-2026-001"}, "ya existe un contrato con ese código"),
    ({"codigo": ""}, "falta «código»"),
    ({"cliente_id": None}, "falta «cliente»"),
])
def test_contrato_validaciones(host, cambio, mensaje):
    cli, _con, _aid = base_comercial(host)
    viejo = run(host, "cliente.crear", nombre="Cliente Archivado")
    run(host, "cliente.archivar", id=viejo)
    valores = {**CONTRATO_OK, "cliente_id": cli, **cambio}
    if valores["cliente_id"] == "archivado":
        valores["cliente_id"] = viejo
    antes = host.db.execute("SELECT COUNT(*) FROM contrato").fetchone()[0]
    with pytest.raises(ValueError) as exc:
        run(host, "contrato.crear", **valores)
    assert str(exc.value) == mensaje
    assert host.db.execute("SELECT COUNT(*) FROM contrato").fetchone()[0] == antes


def test_contrato_editar_combina_con_lo_guardado(host):
    _cli, con, aid = base_comercial(host)
    with pytest.raises(ValueError, match="no puede ser anterior"):
        run(host, "contrato.editar", id=con, hasta="2026-11-15")
    run(host, "contrato.editar", id=con, hasta="2026-12-20", valor_cop="$ 2.000.000")
    c = host.entities.get("contrato", con)
    assert (c["hasta"], c["valor_cop"]) == ("2026-12-20", 2000000)
    run(host, "compromiso.crear", contrato_id=con, asset_id=aid, **PAUTA)
    with pytest.raises(ValueError, match="pautas de este contrato fuera"):
        run(host, "contrato.editar", id=con, hasta="2026-12-10")      # la pauta va hasta el 15


# --- compromiso ------------------------------------------------------------------------------------------------------------
def test_compromiso_fechas_locales_a_utc(host):
    _cli, con, aid = base_comercial(host)
    pid = run(host, "compromiso.crear", contrato_id=con, asset_id=aid, **PAUTA)
    r = host.entities.get("compromiso", pid)
    assert r["plays_required"] == 60 and r["campaign"] == "Navidad"
    assert r["window_start"] == "2026-12-01T05:00:00+00:00" and r["window_end"] == "2026-12-16T05:00:00+00:00"
    assert (r["daypart_start"], r["daypart_end"]) == ("06:00", "10:00")
    assert r["client"] == comercial.CLIENTE_HEREDADO == "(ver contrato)" and r["contrato_id"] == con


def test_compromiso_no_copia_campos(host):
    _cli, con, aid = base_comercial(host)
    pid = run(host, "compromiso.crear", contrato_id=con, asset_id=aid, **PAUTA)
    fila = host.db.execute("SELECT * FROM commitments WHERE id = ?", (pid,)).fetchone()
    assert not any("Cliente Uno" in str(v) or "RRC-2026-001" in str(v) for v in tuple(fila))


@pytest.mark.parametrize("cambio, mensaje", [
    ({"cantidad": 0}, "la cantidad debe ser un número entero, de 1 en adelante"),
    ({"cantidad": 2.5}, "la cantidad debe ser un número entero, de 1 en adelante"),
    ({"cantidad": "muchas"}, "la cantidad debe ser un número entero, de 1 en adelante"),
    ({"desde": "2026-11-30"}, "la pauta debe quedar dentro de la vigencia del contrato (01/12/2026 – 31/12/2026)"),
    ({"hasta": "2027-01-01"}, "la pauta debe quedar dentro de la vigencia del contrato (01/12/2026 – 31/12/2026)"),
    ({"franja_hasta": None}, "la franja necesita «desde» y «hasta», o déjala vacía"),
    ({"franja_desde": "6:00"}, "la hora debe ir como HH:MM, por ejemplo 06:00"),
    ({"franja_hasta": "24:00"}, "la hora debe ir como HH:MM, por ejemplo 06:00"),
    ({"franja_hasta": "10:60"}, "la hora debe ir como HH:MM, por ejemplo 06:00"),
    ({"franja_hasta": "06:00"}, "la franja no puede empezar y terminar a la misma hora"),
    ({"asset_id": "musica"}, "elige una cuña activa de la biblioteca"),
    ({"asset_id": "retirada"}, "elige una cuña activa de la biblioteca"),
    ({"asset_id": None}, "falta «cuña»"),
    ({"contrato_id": "archivado"}, "el contrato está archivado: restáuralo primero"),
    ({"client": "Cliente Uno"}, "«Compromiso» no tiene el campo «client»"),
    ({"contract_ref": "X"}, "«Compromiso» no tiene el campo «contract_ref»"),
    ({"window_start": "2026-12-01T00:00:00Z"}, "«Compromiso» no tiene el campo «window_start»"),
    ({"window_end": "2026-12-01T00:00:00Z"}, "«Compromiso» no tiene el campo «window_end»"),
])
def test_compromiso_validaciones(host, cambio, mensaje):
    cli, con, aid = base_comercial(host)
    otras = {"musica": cuna(host, "Tema", kind="music"), "retirada": cuna(host, "Cuña Vieja", status="retired")}
    viejo = run(host, "contrato.crear", codigo="VIEJO", cliente_id=cli, tipo="pauta", desde="2026-12-01", hasta="2026-12-31")
    run(host, "contrato.archivar", id=viejo)
    valores = {"contrato_id": con, "asset_id": aid, **PAUTA, **cambio}
    if valores.get("asset_id") in otras:
        valores["asset_id"] = otras[valores["asset_id"]]
    if valores["contrato_id"] == "archivado":
        valores["contrato_id"] = viejo
    with pytest.raises(ValueError) as exc:
        run(host, "compromiso.crear", **valores)
    assert str(exc.value) == mensaje
    assert host.db.execute("SELECT COUNT(*) FROM commitments").fetchone()[0] == 0


def test_franja_cruza_medianoche_valida(host):
    _cli, con, aid = base_comercial(host)
    pid = run(host, "compromiso.crear", contrato_id=con, asset_id=aid,
              **{**PAUTA, "franja_desde": "22:00", "franja_hasta": "02:00"})
    assert host.entities.get("compromiso", pid)["daypart_start"] == "22:00"
    sin = run(host, "compromiso.crear", contrato_id=con, asset_id=aid, cantidad=5, desde="2026-12-01", hasta="2026-12-01")
    r = host.entities.get("compromiso", sin)
    assert r["daypart_start"] is None and r["window_end"] == "2026-12-02T05:00:00+00:00"


def test_archivar_con_dependientes(host):
    cli, con, aid = base_comercial(host)
    pid = run(host, "compromiso.crear", contrato_id=con, asset_id=aid, **PAUTA)
    contar = lambda: [host.db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("cliente", "contrato", "commitments")]  # noqa: E731
    antes = contar()
    with pytest.raises(ValueError) as exc:
        run(host, "cliente.archivar", id=cli)
    assert str(exc.value) == "tiene contratos activos: archívalos primero"
    assert host.state["produccion.aviso"] == "No se pudo archivar: tiene contratos activos: archívalos primero."
    with pytest.raises(ValueError) as exc:
        run(host, "contrato.archivar", id=con)
    assert str(exc.value) == "tiene pautas activas: archívalas primero"
    run(host, "compromiso.archivar", id=pid)
    assert host.state["produccion.listo"] == "Pauta archivada. Puedes restaurarla desde «Archivados»."
    run(host, "contrato.archivar", id=con)
    run(host, "cliente.archivar", id=cli)
    assert host.state["produccion.listo"] == "Cliente «Cliente Uno S.A.S.» archivado. Puedes restaurarlo desde «Archivados»."
    with pytest.raises(ValueError) as exc:
        run(host, "compromiso.restaurar", id=pid)
    assert str(exc.value) == "su contrato está archivado: restáuralo primero"
    with pytest.raises(ValueError, match="su cliente está archivado"):
        run(host, "contrato.restaurar", id=con)
    assert contar() == antes
    run(host, "cliente.restaurar", id=cli)
    run(host, "contrato.restaurar", id=con)
    run(host, "compromiso.restaurar", id=pid)
    assert host.state["produccion.listo"] == "Pauta restaurada."
    assert host.entities.list("compromiso")["total"] == 1


# --- REST ---------------------------------------------------------------------------------------------------------------
def test_rest_firma_y_errores_400(tmp_path, monkeypatch):
    monkeypatch.setenv("LEONRADIO_CONFIG", str(tmp_path / "ajustes" / "config.json"))
    monkeypatch.setenv("LEONRADIO_DB", str(tmp_path / "ajustes" / "leonradio.db"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    app = create_app(tick=False, ui_dir=Path("/nonexistent"), addon_dirs=[])
    with TestClient(app) as c:
        r = c.post("/api/commands/cliente.crear", json={"args": {"nombre": "Cliente Uno S.A.S."}})
        assert r.status_code == 200
        assert app.state.host.entities.get("cliente", r.json()["result"])["created_by"] == "local"
        dup = c.post("/api/commands/cliente.crear", json={"args": {"nombre": "cliente uno s.a.s."}})
        assert dup.status_code == 400 and dup.json()["detail"] == "ya existe un cliente con ese nombre"
        bad = c.post("/api/commands/contrato.crear", json={"args": {"codigo": "X", "cliente_id": 2 ** 70, "tipo": "pauta",
                                                                    "desde": "2026-12-01", "hasta": "2026-12-02"}})
        assert bad.status_code == 400 and bad.json()["detail"] == "elige un cliente activo"
        for body in (bad, dup):
            assert "IntegrityError" not in body.text and "sqlite" not in body.text.lower() and "SELECT" not in body.text


# --- panel ---------------------------------------------------------------------------------------------------------------
def _walk(node):
    yield node
    for ch in node.get("children", []):
        yield from _walk(ch)
    for tab in node.get("tabs", []):
        for ch in tab.get("children", []):
            yield from _walk(ch)


def _tab(tree, label):
    tabs = next(n for n in _walk(tree) if n["t"] == "tabs")
    tab = next(t for t in tabs["tabs"] if t["label"] == label)
    return [n for ch in tab["children"] for n in _walk(ch)]


def _textos(nodes):
    return [n.get("text") or n.get("label") for n in nodes if n["t"] in ("label", "button")]


def poblar(host):
    c1 = run(host, "cliente.crear", nombre="Cliente Uno S.A.S.")
    c2 = run(host, "cliente.crear", nombre="Cliente Dos Ltda.")
    k1 = run(host, "contrato.crear", codigo="RRC-2026-001", cliente_id=c1, tipo="patrocinio",
             desde="2026-12-01", hasta="2026-12-31", valor_cop=1500000)
    k2 = run(host, "contrato.crear", codigo="RRC-2026-002", cliente_id=c2, tipo="pauta", desde="2099-01-15", hasta="2099-02-15")
    aid = cuna(host)
    run(host, "compromiso.crear", contrato_id=k1, asset_id=aid, **PAUTA)
    run(host, "compromiso.crear", contrato_id=k2, asset_id=aid, cantidad=10, desde="2099-01-15", hasta="2099-01-20")
    return c1, c2, k1, k2, aid


def test_panel_comercial_tablas_y_formulario(host):
    c1, _c2, k1, _k2, aid = poblar(host)
    assert host.editors["produccion.comercial"][0].station == "produccion"
    tree = host.draw_editor("produccion.comercial")
    tabs = next(n for n in _walk(tree) if n["t"] == "tabs")
    assert [t["label"] for t in tabs["tabs"]] == ["Clientes", "Contratos", "Pauta"]
    for label, n in (("Clientes", 2), ("Contratos", 2), ("Pauta", 2)):
        table = next(x for x in _tab(tree, label) if x["t"] == "table")
        assert len(table["rows"]) == n
        assert all([a["label"] for a in r[-1]["actions"]] == ["Editar", "Archivar"] for r in table["rows"])
    contratos = next(x for x in _tab(tree, "Contratos") if x["t"] == "table")
    assert contratos["columns"] == ["Código", "Cliente", "Tipo", "Vigencia", "Valor", "Estado", "Acciones"]
    fila = next(r for r in contratos["rows"] if r[0] == "RRC-2026-001")
    assert fila[1] == "Cliente Uno S.A.S." and fila[2] == "Patrocinio" and fila[3] == "01/12/2026 – 31/12/2026"
    assert fila[4] == "$ 1.500.000" and fila[5] in ("vigente", "por empezar", "terminado")
    assert next(r for r in contratos["rows"] if r[0] == "RRC-2026-002")[5] == "por empezar"
    pauta = next(x for x in _tab(tree, "Pauta") if x["t"] == "table")
    fila = next(r for r in pauta["rows"] if r[0] == "RRC-2026-001")
    assert fila[1:3] == ["Cliente Uno S.A.S.", "Cuña Prueba"] and fila[5] == "01/12/2026 – 15/12/2026"
    assert fila[6] == "06:00 – 10:00"
    assert next(r for r in pauta["rows"] if r[0] == "RRC-2026-002")[6] == "Todo el día"

    # nuevo contrato: borrador, campo por campo, y «Guardar»
    run(host, "produccion.ver", entidad="contrato")
    nodes = _tab(host.draw_editor("produccion.comercial"), "Contratos")
    form = next(n for n in nodes if n["t"] == "form")
    assert form["command"] == "produccion.campo"
    assert [f["label"] for f in form["fields"]] == ["Código", "Cliente", "Tipo", "Desde", "Hasta", "Valor (COP)", "Descripción"]
    cliente = next(f for f in form["fields"] if f["key"] == "cliente_id")
    assert cliente["kind"] == "select" and cliente["options"][0] == "(elige un cliente)"
    assert cliente["options"][1:] == ["Cliente Dos Ltda.", "Cliente Uno S.A.S."]
    assert {"Guardar", "Cancelar", "Nuevo contrato"} <= set(_textos(nodes))
    for k, v in (("codigo", "rrc-2026-003"), ("cliente_id", "Cliente Uno S.A.S."), ("tipo", "Pauta"),
                 ("desde", "01/12/2026"), ("hasta", "2026-12-31"), ("valor_cop", "$ 800.000"), ("descripcion", "")):
        run(host, "produccion.campo", **{k: v})
    nuevo = run(host, "produccion.guardar")
    c = host.entities.get("contrato", nuevo)
    assert (c["codigo"], c["cliente_id"], c["tipo"], c["desde"], c["hasta"], c["valor_cop"]) == (
        "RRC-2026-003", c1, "pauta", "2026-12-01", "2026-12-31", 800000)
    assert host.state["produccion.sel"] == {"entidad": "contrato", "id": nuevo}
    assert host.state["produccion.listo"] == "Contrato RRC-2026-003 creado."
    nodes = _tab(host.draw_editor("produccion.comercial"), "Contratos")
    textos = _textos(nodes)
    assert "Guardar" not in textos and "Cerrar" in textos and "Contrato RRC-2026-003" in textos
    assert "Contrato RRC-2026-003 creado." in textos
    form = next(n for n in nodes if n["t"] == "form")
    assert {f["key"]: f["value"] for f in form["fields"]}["desde"] == "01/12/2026"

    # edición de una fila existente: cada campo se guarda solo
    run(host, "produccion.ver", entidad="contrato", id=k1)
    run(host, "produccion.campo", hasta="2026-12-20")
    assert host.entities.get("contrato", k1)["hasta"] == "2026-12-20"
    assert host.state["produccion.listo"] is None and host.state["produccion.aviso"] is None

    # pauta: el select de cuñas trae «id · título» y la franja se edita de a un campo
    pid = host.entities.list("compromiso", where={"contrato_id": k1})["items"][0]["id"]
    run(host, "produccion.ver", entidad="compromiso", id=pid)
    form = next(n for n in _tab(host.draw_editor("produccion.comercial"), "Pauta") if n["t"] == "form")
    campos = {f["key"]: f for f in form["fields"]}
    assert campos["asset_id"]["value"] == f"{aid} · Cuña Prueba" and campos["asset_id"]["options"][0] == "(elige una cuña)"
    assert campos["contrato_id"]["value"] == "RRC-2026-001 · Cliente Uno S.A.S."
    assert (campos["desde"]["value"], campos["hasta"]["value"]) == ("01/12/2026", "15/12/2026")


def test_franja_en_pareja_desde_el_panel(host):
    _c1, _c2, k1, _k2, _aid = poblar(host)
    pid = host.entities.list("compromiso", where={"contrato_id": k1})["items"][0]["id"]
    run(host, "produccion.ver", entidad="compromiso", id=pid)
    run(host, "produccion.campo", franja_desde="22:00")          # completa con la «hasta» guardada (10:00)
    assert host.entities.get("compromiso", pid)["daypart_start"] == "22:00"
    with pytest.raises(ValueError, match="la franja necesita"):
        run(host, "produccion.campo", franja_desde="")
    form = next(n for n in _tab(host.draw_editor("produccion.comercial"), "Pauta") if n["t"] == "form")
    assert {f["key"]: f["value"] for f in form["fields"]}["franja_desde"] == ""     # lo escrito no se pierde
    run(host, "produccion.campo", franja_hasta="")
    r = host.entities.get("compromiso", pid)
    assert r["daypart_start"] is None and r["daypart_end"] is None


def test_borrador_guardar_y_aviso(host):
    cli = run(host, "cliente.crear", nombre="Cliente Uno S.A.S.")
    run(host, "contrato.crear", codigo="RRC-2026-001", cliente_id=cli, tipo="pauta", desde="2026-12-01", hasta="2026-12-31")
    run(host, "produccion.ver", entidad="contrato")
    run(host, "produccion.campo", codigo="RRC-2026-009")
    with pytest.raises(ValueError):
        run(host, "produccion.campo", desde="31-12-2026")
    assert host.state["produccion.aviso"] == "No se guardó: «desde» debe ser una fecha, por ejemplo 01/12/2026."
    assert host.state["produccion.sel"]["borrador"]["desde"] == "31-12-2026"         # el texto se conserva
    run(host, "produccion.campo", desde="01/12/2026")
    assert host.state["produccion.aviso"] is None
    antes = host.db.execute("SELECT COUNT(*) FROM contrato").fetchone()[0]
    with pytest.raises(ValueError) as exc:
        run(host, "produccion.guardar")
    assert str(exc.value) == "falta «cliente»"
    assert host.state["produccion.aviso"] == "No se guardó: falta «cliente»."
    assert host.db.execute("SELECT COUNT(*) FROM contrato").fetchone()[0] == antes
    nodes = _tab(host.draw_editor("produccion.comercial"), "Contratos")
    assert any(n["t"] == "label" and n["tone"] == "warn" and n["text"] == "No se guardó: falta «cliente»." for n in nodes)
    run(host, "produccion.campo", cliente_id="(elige un cliente)")
    assert host.state["produccion.aviso"] is None
    run(host, "produccion.campo", cliente_id="Cliente Uno S.A.S.")
    run(host, "produccion.campo", tipo="Patrocinio")
    run(host, "produccion.campo", hasta="15/12/2026")
    nuevo = run(host, "produccion.guardar")
    assert host.entities.get("contrato", nuevo)["tipo"] == "patrocinio"
    # en edición, un campo inválido no se guarda y deja el aviso
    with pytest.raises(ValueError):
        run(host, "produccion.campo", hasta="30/11/2026")
    assert host.state["produccion.aviso"] == "No se guardó: «hasta» no puede ser anterior a «desde»."
    assert host.entities.get("contrato", nuevo)["hasta"] == "2026-12-15"
    run(host, "produccion.cerrar")
    assert host.state["produccion.sel"] is None and host.state["produccion.aviso"] is None


def test_confirmar_archivar_y_estados_vacios(host):
    tree = host.draw_editor("produccion.comercial")
    assert "Aún no hay clientes." in _textos(_tab(tree, "Clientes"))
    assert "Primero crea un cliente en la pestaña «Clientes»." in _textos(_tab(tree, "Contratos"))
    assert "Nuevo contrato" not in _textos(_tab(tree, "Contratos"))
    c1, _c2, k1, _k2, _aid = poblar(host)
    run(host, "produccion.ver", entidad="cliente", id=c1, archivar=True)
    textos = _textos(_tab(host.draw_editor("produccion.comercial"), "Clientes"))
    assert "No se puede archivar todavía" in textos and "Archivar" not in textos[:textos.index("Entendido")]
    assert "«Cliente Uno S.A.S.» tiene 1 contrato activo. Archívalo primero." in textos
    pid = host.entities.list("compromiso", where={"contrato_id": k1})["items"][0]["id"]
    run(host, "produccion.ver", entidad="compromiso", id=pid, archivar=True)
    nodes = _tab(host.draw_editor("produccion.comercial"), "Pauta")
    assert "¿Archivar esta pauta?" in _textos(nodes)
    boton = next(n for n in nodes if n["t"] == "button" and n["label"] == "Archivar")
    host.run_command(boton["command"], boton["args"])
    assert host.state["produccion.sel"] is None
    run(host, "produccion.archivados", entidad="compromiso", ver=True)
    nodes = _tab(host.draw_editor("produccion.comercial"), "Pauta")
    table = next(n for n in nodes if n["t"] == "table")
    assert [a["label"] for a in table["rows"][0][-1]["actions"]] == ["Restaurar"]
    assert "Nueva pauta" not in _textos(nodes)


def test_paginacion(host):
    for i in range(55):
        run(host, "cliente.crear", nombre=f"Cliente {i:03d}")
    nodes = _tab(host.draw_editor("produccion.comercial"), "Clientes")
    assert len(next(n for n in nodes if n["t"] == "table")["rows"]) == 50
    assert "1–50 de 55" in _textos(nodes) and "Siguientes" in _textos(nodes) and "Anteriores" not in _textos(nodes)
    run(host, "produccion.pagina", entidad="cliente", offset=50)
    nodes = _tab(host.draw_editor("produccion.comercial"), "Clientes")
    assert len(next(n for n in nodes if n["t"] == "table")["rows"]) == 5 and "51–55 de 55" in _textos(nodes)


def test_panel_sin_nombre_del_dueno(host):
    poblar(host)
    for state in ({}, {"entidad": "contrato"}, {"entidad": "compromiso"}):
        if state:
            run(host, "produccion.ver", **state)
        assert "Jonathan" not in json.dumps(host.draw_editor("produccion.comercial"), ensure_ascii=False)
