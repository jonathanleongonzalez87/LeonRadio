"""Reglas comerciales de Producción (A6a): clientes, contratos y compromisos de pauta.

Capa propia en vez de `register_crud`: las validaciones combinadas (vigencias, franja, dependientes) no se pueden saltar
por `<entidad>.editar`. Los mensajes van con las etiquetas del formulario («código»), nunca con nombres de columna ni SQL.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ... import entities, sdk

CLIENTE_HEREDADO = "(ver contrato)"     # `commitments.client` es NOT NULL desde v1: el cliente real sale de contrato_id
NOMBRE = {"cliente": "Cliente", "contrato": "Contrato", "compromiso": "Compromiso"}
CLAVES = {
    "cliente": ("nombre", "notas"),
    "contrato": ("codigo", "cliente_id", "tipo", "desde", "hasta", "valor_cop", "descripcion"),
    "compromiso": ("contrato_id", "asset_id", "campana", "cantidad", "desde", "hasta", "franja_desde", "franja_hasta", "notas"),
}
OBLIGATORIOS = {
    "cliente": ("nombre",),
    "contrato": ("codigo", "cliente_id", "tipo", "desde", "hasta"),
    "compromiso": ("contrato_id", "asset_id", "cantidad", "desde", "hasta"),
}
ETIQUETA = {     # clave de la API o columna → etiqueta del formulario
    "cliente": {"nombre": "nombre", "nombre_norm": "nombre", "notas": "notas"},
    "contrato": {"codigo": "código", "cliente_id": "cliente", "tipo": "tipo", "desde": "desde", "hasta": "hasta",
                 "valor_cop": "valor", "descripcion": "descripción"},
    "compromiso": {"contrato_id": "contrato", "asset_id": "cuña", "campana": "campaña", "campaign": "campaña",
                   "cantidad": "cantidad", "plays_required": "cantidad", "desde": "desde", "hasta": "hasta",
                   "window_start": "desde", "window_end": "hasta", "franja_desde": "franja desde",
                   "franja_hasta": "franja hasta", "daypart_start": "franja desde", "daypart_end": "franja hasta",
                   "notas": "notas", "notes": "notas"},
}
INESPERADO = ("ocurrió un problema al guardar. Vuelve a intentarlo; si sigue igual, avisa a quien administra la "
              "plataforma")
FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FECHA_LOCAL = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
HORA = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FRANJA = ("franja_desde", "franja_hasta")


# -- fechas y zona -------------------------------------------------------------------------------------------------
def zona(config) -> ZoneInfo | None:
    """Zona de la emisora; `None` si el sistema no trae la base de zonas: se usa la del equipo (como Al Aire)."""
    try:
        return ZoneInfo(config["timezone"])
    except Exception:  # noqa: BLE001
        return None


def hoy(tz) -> date:
    return (datetime.now(tz) if tz else datetime.now().astimezone()).date()


def _medianoche(d: date, tz) -> str:
    local = datetime(d.year, d.month, d.day, tzinfo=tz) if tz else datetime(d.year, d.month, d.day).astimezone()
    return local.astimezone(timezone.utc).isoformat()


def local(stamp: str, tz) -> datetime:
    dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz) if tz else dt.astimezone()


def dia_inicio(stamp: str, tz) -> date:
    return local(stamp, tz).date()


def dia_final(stamp: str, tz) -> date:
    """Último día incluido de una vigencia que termina en `stamp` (exclusivo): si es medianoche, el día anterior."""
    dt = local(stamp, tz)
    return dt.date() - timedelta(days=1) if dt.time() == datetime.min.time() else dt.date()


def fecha_corta(d: date | str) -> str:
    return (date.fromisoformat(d) if isinstance(d, str) else d).strftime("%d/%m/%Y")


# -- valores -------------------------------------------------------------------------------------------------------
def _vacio(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _fecha(v, etiqueta: str) -> date:
    if isinstance(v, str) and FECHA.match(v.strip()):
        try:
            return date.fromisoformat(v.strip())
        except ValueError:
            pass
    raise ValueError(f"«{etiqueta}» debe ser una fecha, por ejemplo 01/12/2026")


def _hora(v) -> str:
    if isinstance(v, str) and HORA.match(v.strip()):
        return v.strip()
    raise ValueError("la hora debe ir como HH:MM, por ejemplo 06:00")


def _valor(v) -> int:
    malo = "el valor debe ser un monto en pesos, por ejemplo 1.500.000"
    if isinstance(v, bool):
        raise ValueError(malo)
    if isinstance(v, float):
        if v != int(v):
            raise ValueError("el valor va en pesos, sin centavos")
        v = int(v)
    if isinstance(v, int):
        if v < 0:
            raise ValueError(malo)
        return v
    if not isinstance(v, str):
        raise ValueError(malo)
    s = "".join(v.replace("$", "").split()).replace(".", "")
    if "," in s:
        raise ValueError("el valor va en pesos, sin centavos")
    if not re.fullmatch(r"[0-9]{1,18}", s):
        raise ValueError(malo)
    return int(s)


def _cantidad(v) -> int:
    malo = ValueError("la cantidad debe ser un número entero, de 1 en adelante")
    if isinstance(v, bool):
        raise malo
    if isinstance(v, float) and v == int(v):
        v = int(v)
    if isinstance(v, str) and re.fullmatch(r"\s*[0-9]{1,9}\s*", v):
        v = int(v)
    if not isinstance(v, int) or not 1 <= v <= 10 ** 9:
        raise malo
    return v


def _fila(reg, entidad: str, id, si_falta: str) -> dict:
    try:
        return reg.get(entidad, entities.check_id(id))
    except ValueError:
        raise ValueError(si_falta) from None


# -- preparar: valores de la API → columnas validadas ------------------------------------------------------------------
def preparar(reg, tz, entidad: str, actual: dict | None, valores: dict, parcial: bool = False) -> dict:
    """Valores de la API (vocabulario del usuario) → columnas validadas. `actual` = fila guardada al editar.
    `parcial=True` (borrador del panel): solo el formato de lo que llega, sin obligatorios ni combinaciones."""
    for k in valores:
        if k not in CLAVES[entidad]:
            raise ValueError(f"«{NOMBRE[entidad]}» no tiene el campo «{k}»")
    v = {k: (None if _vacio(x) else x) for k, x in valores.items()}
    if not parcial:
        for k in OBLIGATORIOS[entidad]:
            if (actual is None and v.get(k) is None) or (k in v and v[k] is None):
                raise ValueError(f"falta «{ETIQUETA[entidad][k]}»")
    return {"cliente": _cliente, "contrato": _contrato, "compromiso": _compromiso}[entidad](reg, tz, actual, v, parcial)


def _cliente(reg, tz, actual, v, parcial) -> dict:
    nombre = v.get("nombre")
    if isinstance(nombre, str):
        otros = reg.list("cliente", where={"nombre_norm": entities.norm(nombre)}, include_archived=True, limit=1)["items"]
        if otros and (actual is None or otros[0]["id"] != actual["id"]):
            raise ValueError("ya existe un cliente con ese nombre")
    return dict(v)


def _contrato(reg, tz, actual, v, parcial) -> dict:
    out = dict(v)
    if isinstance(v.get("codigo"), str):
        out["codigo"] = v["codigo"].strip().upper()
        otros = reg.list("contrato", where={"codigo": out["codigo"]}, include_archived=True, limit=1)["items"]
        if otros and (actual is None or otros[0]["id"] != actual["id"]):
            raise ValueError("ya existe un contrato con ese código")
    if v.get("cliente_id") is not None:
        if _fila(reg, "cliente", v["cliente_id"], "elige un cliente activo")["archived"]:
            raise ValueError("elige un cliente activo")
    if v.get("tipo") is not None:
        tipo = v["tipo"].strip().lower() if isinstance(v["tipo"], str) else None
        if tipo not in ("pauta", "patrocinio"):
            raise ValueError("el tipo debe ser «pauta» o «patrocinio»")
        out["tipo"] = tipo
    for k in ("desde", "hasta"):
        if v.get(k) is not None:
            out[k] = _fecha(v[k], k).isoformat()
    if v.get("valor_cop") is not None:
        out["valor_cop"] = _valor(v["valor_cop"])
    if parcial or not ({"desde", "hasta"} & set(v)):
        return out
    d = date.fromisoformat(out.get("desde") or actual["desde"])
    h = date.fromisoformat(out.get("hasta") or actual["hasta"])
    if h < d:
        raise ValueError("«hasta» no puede ser anterior a «desde»")
    if actual is not None:                      # las pautas activas del contrato deben seguir dentro de la vigencia
        for c in todas(reg, "compromiso", where={"contrato_id": actual["id"]}):
            if dia_inicio(c["window_start"], tz) < d or dia_final(c["window_end"], tz) > h:
                raise ValueError("hay pautas de este contrato fuera de esa vigencia: ajústalas primero")
    return out


def _compromiso(reg, tz, actual, v, parcial) -> dict:
    out: dict = {}
    for api, col in (("campana", "campaign"), ("notas", "notes")):
        if api in v:
            out[col] = v[api]
    if v.get("cantidad") is not None:
        out["plays_required"] = _cantidad(v["cantidad"])
    contrato = None
    if v.get("contrato_id") is not None:
        contrato = _fila(reg, "contrato", v["contrato_id"], "elige un contrato activo")
        if contrato["archived"]:
            raise ValueError("el contrato está archivado: restáuralo primero")
        out["contrato_id"] = contrato["id"]
    if v.get("asset_id") is not None:
        pieza = _fila(reg, "pieza", v["asset_id"], "elige una cuña activa de la biblioteca")
        if pieza["kind"] != "spot" or pieza["status"] != "active":
            raise ValueError("elige una cuña activa de la biblioteca")
        out["asset_id"] = pieza["id"]
    elif "asset_id" in v:
        out["asset_id"] = None
    fechas = {k: _fecha(v[k], k) for k in ("desde", "hasta") if v.get(k) is not None}
    if "desde" in fechas:
        out["window_start"] = _medianoche(fechas["desde"], tz)
    if "hasta" in fechas:
        out["window_end"] = _medianoche(fechas["hasta"] + timedelta(days=1), tz)
    for k, col in zip(FRANJA, ("daypart_start", "daypart_end")):
        if k in v:
            out[col] = None if v[k] is None else _hora(v[k])
    if parcial:
        return out
    if {"desde", "hasta", "contrato_id"} & set(v):
        d = fechas.get("desde") or dia_inicio(actual["window_start"], tz)
        h = fechas.get("hasta") or dia_final(actual["window_end"], tz)
        if h < d:
            raise ValueError("«hasta» no puede ser anterior a «desde»")
        if contrato is None and actual is not None and actual.get("contrato_id"):
            contrato = reg.get("contrato", actual["contrato_id"])
            if contrato["archived"]:
                raise ValueError("el contrato está archivado: restáuralo primero")
        if contrato is not None:
            cd, ch = date.fromisoformat(contrato["desde"]), date.fromisoformat(contrato["hasta"])
            if d < cd or h > ch:
                raise ValueError(f"la pauta debe quedar dentro de la vigencia del contrato "
                                 f"({fecha_corta(cd)} – {fecha_corta(ch)})")
    if set(FRANJA) & set(v):
        fd = out["daypart_start"] if "daypart_start" in out else (actual or {}).get("daypart_start")
        fh = out["daypart_end"] if "daypart_end" in out else (actual or {}).get("daypart_end")
        if (fd is None) != (fh is None):
            raise ValueError("la franja necesita «desde» y «hasta», o déjala vacía")
        if fd is not None and fd == fh:
            raise ValueError("la franja no puede empezar y terminar a la misma hora")
    return out


def todas(reg, entidad: str, **kw) -> list[dict]:
    """Todas las páginas de una lista (decenas o cientos de filas)."""
    items: list[dict] = []
    while True:
        page = reg.list(entidad, limit=200, offset=len(items), **kw)
        items += page["items"]
        if not page["items"] or len(items) >= page["total"]:
            return items


# -- escritura -------------------------------------------------------------------------------------------------------
def _mensaje(entidad: str, exc: ValueError) -> ValueError:
    """El `Writer` nombra columnas («codigo»): se pasan a la etiqueta del formulario («código»)."""
    text = str(exc)
    if text.startswith(f"«{NOMBRE[entidad]}» no tiene el campo"):     # la clave que mandó quien llama, tal cual
        return ValueError(text)
    if text == "ya existe un registro igual":
        text = {"cliente": "ya existe un cliente con ese nombre", "contrato": "ya existe un contrato con ese código"}.get(
            entidad, text)
    for col, etiqueta in sorted(ETIQUETA[entidad].items(), key=lambda kv: -len(kv[0])):
        text = text.replace(f"«{col}»", f"«{etiqueta}»")
    return ValueError(text)


def _seguro(entidad: str, fn):
    try:
        return fn()
    except ValueError as exc:
        raise _mensaje(entidad, exc) from None
    except sqlite3.Error as exc:
        sdk.log.warning("Producción: no se pudo guardar (%s)", type(exc).__name__)
        raise ValueError(INESPERADO) from None


def crear(host, entidad: str, valores: dict, who: str) -> int:
    def run() -> int:
        limpio = preparar(host.entities, zona(host.config), entidad, None, valores)
        if entidad == "compromiso":
            limpio["client"] = CLIENTE_HEREDADO
        return host.entities.writer("produccion").create(entidad, limpio, who=who)
    return _seguro(entidad, run)


def editar(host, entidad: str, id, valores: dict, who: str) -> None:
    def run() -> None:
        actual = host.entities.get(entidad, entities.check_id(id))
        limpio = preparar(host.entities, zona(host.config), entidad, actual, valores)
        if limpio:
            host.entities.writer("produccion").update(entidad, id, limpio, who=who)
    _seguro(entidad, run)


def archivar(host, entidad: str, id, who: str) -> None:
    reg = host.entities

    def run() -> None:
        entities.check_id(id)
        if entidad == "cliente" and reg.list("contrato", where={"cliente_id": id}, limit=1)["total"]:
            raise ValueError("tiene contratos activos: archívalos primero")
        if entidad == "contrato" and reg.list("compromiso", where={"contrato_id": id}, limit=1)["total"]:
            raise ValueError("tiene pautas activas: archívalas primero")
        reg.writer("produccion").archive(entidad, id, who=who)
    _seguro(entidad, run)


def restaurar(host, entidad: str, id, who: str) -> None:
    reg = host.entities

    def run() -> None:
        fila = reg.get(entidad, entities.check_id(id))
        if entidad == "compromiso" and fila["contrato_id"] and reg.get("contrato", fila["contrato_id"])["archived"]:
            raise ValueError("su contrato está archivado: restáuralo primero")
        if entidad == "contrato" and reg.get("cliente", fila["cliente_id"])["archived"]:
            raise ValueError("su cliente está archivado: restáuralo primero")
        reg.writer("produccion").restore(entidad, id, who=who)
    _seguro(entidad, run)


def nombre_de(entidad: str, fila: dict) -> str:
    """Cómo se nombra un registro en los avisos: «Cliente «X»», «Contrato RRC-1», «Pauta»."""
    if entidad == "cliente":
        return f"Cliente «{fila['nombre']}»"
    if entidad == "contrato":
        return f"Contrato {fila['codigo']}"
    return "Pauta"


def _hecho(entidad: str, masculino: str) -> str:
    return masculino if entidad != "compromiso" else masculino[:-1] + "a"


# -- estado del panel (una selección por servidor, como el explorador) --------------------------------------------------
def avisar(ctx, entidad: str | None, aviso: str | None = None, listo: str | None = None) -> None:
    ctx.set_state("produccion.aviso", aviso)
    ctx.set_state("produccion.listo", listo)
    ctx.set_state("produccion.aviso_de", entidad)


def _entidad(entidad) -> str:
    if entidad not in NOMBRE:
        raise ValueError("entidad desconocida")
    return entidad


def del_formulario(reg, entidad: str, clave: str, raw):
    """Texto de un campo del panel → valor de la API (los select muestran nombres; la API usa ids y AAAA-MM-DD)."""
    if not isinstance(raw, str):
        return raw
    if raw.startswith("(elige"):
        return None
    texto = raw.strip()
    if not texto:
        return None
    if clave == "cliente_id":
        hallado = reg.list("cliente", where={"nombre_norm": entities.norm(texto)}, limit=1)["items"]
        if not hallado:
            raise ValueError("elige un cliente activo")
        return hallado[0]["id"]
    if clave == "contrato_id":
        hallado = reg.list("contrato", where={"codigo": texto.split(" · ")[0].strip().upper()}, include_archived=True,
                           limit=1)["items"]
        if not hallado:
            raise ValueError("elige un contrato activo")
        return hallado[0]["id"]
    if clave == "asset_id":
        m = re.match(r"^(\d{1,18}) · ", texto)
        if not m:
            raise ValueError("elige una cuña activa de la biblioteca")
        return int(m.group(1))
    if clave in ("desde", "hasta"):
        m = FECHA_LOCAL.match(texto)
        if m:
            try:
                return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
            except ValueError:
                raise ValueError(f"«{clave}» debe ser una fecha, por ejemplo 01/12/2026") from None
    return texto


def register(host: sdk.Host) -> None:
    reg = host.entities
    tz = lambda: zona(host.config)  # noqa: E731

    def make(entidad: str) -> None:
        host.register_command(f"{entidad}.crear", lambda ctx, **valores: crear(host, entidad, valores, ctx.principal),
                              risk="datos")
        host.register_command(f"{entidad}.editar",
                              lambda ctx, id, **valores: editar(host, entidad, id, valores, ctx.principal), risk="datos")

        def archivar_cmd(ctx, id) -> None:
            try:
                archivar(host, entidad, id, ctx.principal)
            except ValueError as exc:
                avisar(ctx, entidad, aviso=f"No se pudo archivar: {exc}.")
                raise
            como = nombre_de(entidad, reg.get(entidad, id))
            suf = "la" if entidad == "compromiso" else "lo"
            avisar(ctx, entidad, listo=f"{como} {_hecho(entidad, 'archivado')}. Puedes restaurar{suf} desde «Archivados».")
            ctx.set_state("produccion.sel", None)

        def restaurar_cmd(ctx, id) -> None:
            try:
                restaurar(host, entidad, id, ctx.principal)
            except ValueError as exc:
                avisar(ctx, entidad, aviso=f"No se pudo restaurar: {exc}.")
                raise
            avisar(ctx, entidad, listo=f"{nombre_de(entidad, reg.get(entidad, id))} {_hecho(entidad, 'restaurado')}.")
            ctx.set_state("produccion.sel", None)

        host.register_command(f"{entidad}.archivar", archivar_cmd, risk="datos")
        host.register_command(f"{entidad}.restaurar", restaurar_cmd, risk="datos")

    for entidad in NOMBRE:
        make(entidad)

    def ver(ctx, entidad, id=None, archivar=False) -> None:
        entidad = _entidad(entidad)
        if id is not None:
            reg.get(entidad, entities.check_id(id))
        elif archivar:
            raise ValueError("elige qué archivar")
        sel = {"entidad": entidad, "id": id}
        if id is None:
            sel["borrador"] = {}
        if archivar:
            sel["archivar"] = True
        ctx.set_state("produccion.sel", sel)
        avisar(ctx, None)

    def cerrar(ctx) -> None:
        ctx.set_state("produccion.sel", None)
        avisar(ctx, None)

    def campo(ctx, **valores) -> None:
        sel = ctx.state.get("produccion.sel")
        if not sel or sel.get("archivar"):
            raise ValueError("elige primero qué editar")
        entidad = sel["entidad"]
        try:
            if sel["id"] is None:                       # borrador: se anota lo escrito (no se pierde) y se valida el formato
                preparar(reg, tz(), entidad, None, {k: None for k in valores}, parcial=True)   # solo claves conocidas
                sel = {**sel, "borrador": {**sel["borrador"], **valores}}
                ctx.set_state("produccion.sel", sel)
                api = {k: del_formulario(reg, entidad, k, raw) for k, raw in valores.items()}
                _seguro(entidad, lambda: preparar(reg, tz(), entidad, None, api, parcial=True))
            else:
                api = {k: del_formulario(reg, entidad, k, raw) for k, raw in valores.items()}
                pendiente = dict(sel.get("pendiente") or {})
                if entidad == "compromiso" and set(FRANJA) & set(api):
                    # la franja va en pareja y el formulario manda un campo por vez: se completa con lo anotado o lo guardado
                    actual = reg.get("compromiso", sel["id"])
                    guardado = {"franja_desde": actual["daypart_start"], "franja_hasta": actual["daypart_end"]}
                    for k in FRANJA:
                        api.setdefault(k, pendiente.get(k, guardado[k]))
                    try:
                        editar(host, entidad, sel["id"], api, ctx.principal)
                    except ValueError as exc:
                        if str(exc).startswith("la franja necesita"):
                            pendiente.update({k: valores[k] for k in FRANJA if k in valores})
                            ctx.set_state("produccion.sel", {**sel, "pendiente": pendiente})
                        raise
                    for k in FRANJA:
                        pendiente.pop(k, None)
                    ctx.set_state("produccion.sel", {**sel, "pendiente": pendiente})
                else:
                    editar(host, entidad, sel["id"], api, ctx.principal)
        except ValueError as exc:
            avisar(ctx, entidad, aviso=f"No se guardó: {_mensaje(entidad, exc)}.")
            raise
        avisar(ctx, None)

    def guardar(ctx) -> int:
        sel = ctx.state.get("produccion.sel")
        if not sel or sel.get("id") is not None or sel.get("archivar"):
            raise ValueError("no hay nada nuevo que guardar")
        entidad = sel["entidad"]
        try:
            api = {k: del_formulario(reg, entidad, k, raw) for k, raw in sel["borrador"].items()}
            nuevo = crear(host, entidad, api, ctx.principal)
        except ValueError as exc:
            avisar(ctx, entidad, aviso=f"No se guardó: {_mensaje(entidad, exc)}.")
            raise
        ctx.set_state("produccion.sel", {"entidad": entidad, "id": nuevo})
        avisar(ctx, entidad, listo=f"{nombre_de(entidad, reg.get(entidad, nuevo))} {_hecho(entidad, 'creado')}.")
        return nuevo

    def archivados(ctx, entidad, ver=None) -> None:
        entidad = _entidad(entidad)
        estado = dict(ctx.state.get("produccion.archivados") or {})
        estado[entidad] = (not estado.get(entidad)) if ver is None else bool(ver)
        ctx.set_state("produccion.archivados", estado)
        ctx.set_state("produccion.offset", {**(ctx.state.get("produccion.offset") or {}), entidad: 0})

    def pagina(ctx, entidad, offset) -> None:
        entidad = _entidad(entidad)
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ValueError("la página no es válida")
        ctx.set_state("produccion.offset", {**(ctx.state.get("produccion.offset") or {}), entidad: max(0, min(offset, 2 ** 62))})

    for name, fn, risk in (("produccion.ver", ver, "normal"), ("produccion.cerrar", cerrar, "normal"),
                           ("produccion.campo", campo, "datos"), ("produccion.guardar", guardar, "datos"),
                           ("produccion.archivados", archivados, "normal"), ("produccion.pagina", pagina, "normal")):
        host.register_command(name, fn, risk=risk)
