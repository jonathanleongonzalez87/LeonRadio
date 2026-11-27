"""Entidades compartidas (S8): cada una tiene una estación dueña que es la única que la escribe.

Ningún nombre de tabla o columna llega a SQL desde una petición: todos salen de las declaraciones (`Entity`, `Field`),
validadas con `IDENT` al declararlas; los valores van siempre como parámetros `?`. Ver docs/entidades.md.
"""

from __future__ import annotations

import contextlib
import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Iterator

from . import sdk

log = logging.getLogger("leonradio.entities")

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
TYPES = ("text", "int", "real", "bool", "date", "datetime")
STD_COLUMNS = ("archived", "created_at", "updated_at", "created_by", "updated_by")
MAX_LIMIT = 200
INT64 = (-(2 ** 63), 2 ** 63 - 1)


def check_id(id: object) -> int:
    """Un id válido es un entero (no bool) de 64 bits: lo demás nunca llega a SQL."""
    if isinstance(id, bool) or not isinstance(id, int) or not INT64[0] <= id <= INT64[1]:
        raise ValueError("el id no es válido")
    return id


def _check_text(text: str, label: str) -> str:
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"«{label}» tiene caracteres no válidos") from None
    return text


@dataclass(frozen=True)
class Field:
    name: str
    type: str = "text"
    required: bool = False
    ref: str | None = None            # nombre de otra entidad: el valor es su id
    choices: tuple[str, ...] | None = None
    unique: bool = False              # solo documenta; el UNIQUE vive en la migración (check_declaration lo comprueba)
    derived_from: str | None = None   # lo calcula el servicio (p. ej. nombre_norm); quien llama no lo envía
    max_len: int = 200


@dataclass(frozen=True)
class Entity:
    name: str
    table: str
    owner: str
    label: str
    about: str
    fields: tuple[Field, ...]         # SOLO lo que se expone y se puede escribir (las columnas estándar no se declaran)
    title: str = "nombre"
    managed: bool = True              # False = tabla anterior al marco: el servicio solo la lee
    active_sql: str | None = None     # solo managed=False: condición fija escrita en código para contar «activos»
    note: str = ""


def norm(text: str) -> str:
    """Forma comparable de un texto: NFC, sin espacios de más y sin distinguir mayúsculas ni tildes de mayúscula."""
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class Registry:
    def __init__(self, host: "sdk.Host") -> None:
        self._host = host
        self._entities: dict[str, Entity] = {}
        self._depth = 0
        self._pending: list[dict] = []

    # -- declaración ---------------------------------------------------------
    def declare(self, entity: Entity) -> None:
        from .estaciones import STATIONS

        for label, value in (("el nombre", entity.name), ("la tabla", entity.table)):
            if not IDENT.match(value):
                raise ValueError(f"{label} «{value}» no es un identificador válido (minúsculas, números y _)")
        if entity.owner not in STATIONS:
            raise ValueError(f"el dueño «{entity.owner}» no es una estación")
        if entity.name in self._entities or any(e.table == entity.table for e in self._entities.values()):
            raise ValueError(f"la entidad «{entity.name}» (o su tabla) ya está declarada")
        names = [f.name for f in entity.fields]
        if len(set(names)) != len(names):
            raise ValueError(f"«{entity.name}» repite un campo")
        reserved = {"id", *STD_COLUMNS}
        for f in entity.fields:
            if not IDENT.match(f.name) or f.name in reserved:
                raise ValueError(f"el campo «{f.name}» no es un identificador válido")
            if f.type not in TYPES:
                raise ValueError(f"el campo «{f.name}» tiene un tipo desconocido")
            if f.derived_from and f.derived_from not in names:
                raise ValueError(f"el campo «{f.name}» se deriva de «{f.derived_from}», que no existe")
        if entity.title not in names:
            raise ValueError(f"el título «{entity.title}» no es un campo de «{entity.name}»")
        self._entities[entity.name] = entity

    def validate(self) -> None:
        for e in self._entities.values():
            for f in e.fields:
                if f.ref and f.ref not in self._entities:
                    raise ValueError(f"«{e.name}.{f.name}» apunta a «{f.ref}», que no está declarada")

    def get_entity(self, name: str) -> Entity:
        try:
            return self._entities[name]
        except KeyError:
            raise ValueError("entidad desconocida") from None

    def all(self) -> list[Entity]:
        return list(self._entities.values())

    # -- lectura (cualquiera) --------------------------------------------------
    @staticmethod
    def _columns(e: Entity) -> list[str]:
        cols = ["id", *(f.name for f in e.fields)]
        return cols + list(STD_COLUMNS) if e.managed else cols

    def list(self, name: str, *, limit: int = 50, offset: int = 0, include_archived: bool = False,
             where: dict | None = None) -> dict:
        e = self.get_entity(name)
        limit, offset = max(1, min(int(limit), MAX_LIMIT)), max(0, min(int(offset), 2 ** 62))
        names = {f.name for f in e.fields} | {"id"}
        conds, params = [], []
        for col, value in (where or {}).items():
            if col not in names:
                raise ValueError(f"«{e.label}» no tiene el campo «{col}»")
            if value is not None and not isinstance(value, (bool, int, float, str)):
                raise ValueError(f"el valor de «{col}» no es válido")
            if isinstance(value, int) and not isinstance(value, bool):
                check_id(value)
            if isinstance(value, str):
                _check_text(value, col)
            conds.append(f"{col} = ?")
            params.append(value)
        if not include_archived:
            if e.managed:
                conds.append("archived = 0")
            elif e.active_sql:
                conds.append(f"({e.active_sql})")
        clause = (" WHERE " + " AND ".join(conds)) if conds else ""
        with self._host.db_lock:
            total = self._host.db.execute(f"SELECT COUNT(*) FROM {e.table}{clause}", params).fetchone()[0]
            rows = self._host.db.execute(
                f"SELECT {', '.join(self._columns(e))} FROM {e.table}{clause} ORDER BY {e.title}, id LIMIT ? OFFSET ?",
                (*params, limit, offset)).fetchall()
        return {"items": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset}

    def get(self, name: str, id: int) -> dict:
        e = self.get_entity(name)
        check_id(id)
        with self._host.db_lock:
            row = self._host.db.execute(
                f"SELECT {', '.join(self._columns(e))} FROM {e.table} WHERE id = ?", (id,)).fetchone()
        if row is None:
            raise ValueError("no existe")
        return dict(row)

    def catalog(self) -> list[dict]:
        out = []
        for e in self._entities.values():
            with self._host.db_lock:
                total = self._host.db.execute(f"SELECT COUNT(*) FROM {e.table}").fetchone()[0]
                if e.managed:
                    active = self._host.db.execute(f"SELECT COUNT(*) FROM {e.table} WHERE archived = 0").fetchone()[0]
                elif e.active_sql:
                    active = self._host.db.execute(f"SELECT COUNT(*) FROM {e.table} WHERE {e.active_sql}").fetchone()[0]
                else:
                    active = total
            out.append({"nombre": e.name, "etiqueta": e.label, "que_es": e.about, "dueno": e.owner,
                        "estado": "gestionada" if e.managed else "solo lectura", "nota": e.note,
                        "campos": [f.name for f in e.fields], "activos": active, "archivados": total - active})
        return out

    # -- escritura ---------------------------------------------------------------
    def writer(self, station: str) -> "Writer":
        from .estaciones import STATIONS

        if station not in STATIONS:
            raise ValueError(f"«{station}» no es una estación")
        return Writer(self, station)

    @contextlib.contextmanager
    def transaction(self) -> Iterator[None]:
        """Varias escrituras, un commit (rollback si algo falla). Los eventos salen una sola vez, al cerrar."""
        with self._host.db_lock:
            if self._depth == 0:
                self._host.db.commit()           # lo ya escrito por otros queda aparte: el rollback solo deshace lo nuestro
            self._depth += 1
            try:
                yield
            except BaseException:
                self._depth -= 1
                if self._depth == 0:
                    self._host.db.rollback()
                    self._pending.clear()
                raise
            self._depth -= 1
            if self._depth == 0:
                self._host.db.commit()
                events, self._pending = self._pending, []
                for ev in _merge(events):
                    self._host.events.emit("entities.changed", ev)

    def _queue(self, entity: str, id: int, action: str) -> None:
        self._pending.append({"entity": entity, "id": id, "action": action})


def _merge(events: list[dict]) -> list[dict]:
    """Un evento por entidad y acción; con muchas filas (`id` distinto) el panel solo necesita saber que cambió."""
    seen: dict[tuple[str, str], dict] = {}
    for ev in events:
        key = (ev["entity"], ev["action"])
        seen[key] = ev if key not in seen else {**ev, "id": None}
    return list(seen.values())


class Writer:
    """Única vía de escritura. Cada método exige que la estación sea la dueña de la entidad."""

    def __init__(self, registry: Registry, station: str) -> None:
        self._reg, self.station = registry, station

    def _entity(self, name: str) -> Entity:
        e = self._reg.get_entity(name)
        if e.owner != self.station:
            from .estaciones import STATIONS

            raise sdk.PermissionDenied(f"«{e.label}» la escribe {STATIONS[e.owner]['nombre']}")
        if not e.managed:
            raise ValueError("esa información la mantiene el sistema")
        return e

    def _clean(self, e: Entity, values: dict, creating: bool) -> dict:
        fields = {f.name: f for f in e.fields}
        out: dict[str, Any] = {}
        for key, raw in values.items():
            f = fields.get(key)
            if f is None or f.derived_from:
                raise ValueError(f"«{e.label}» no tiene el campo «{key}»")
            out[key] = self._value(e, f, raw)
        for f in e.fields:
            if f.derived_from and f.derived_from in out:
                src = out[f.derived_from]
                out[f.name] = norm(src) if src is not None else None
            if f.required and not f.derived_from and (creating or f.name in out) and out.get(f.name) is None:
                raise ValueError(f"falta «{f.name}»")
        return out

    def _value(self, e: Entity, f: Field, raw: Any) -> Any:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        if isinstance(raw, str):
            _check_text(raw, f.name)
        elif not isinstance(raw, (bool, int, float)):
            raise ValueError(f"«{f.name}» no es un valor válido")
        try:
            if f.type == "int" or f.ref:
                if isinstance(raw, bool) or (isinstance(raw, float) and raw != int(raw)):
                    raise ValueError
                v: Any = int(raw)
                if not INT64[0] <= v <= INT64[1]:
                    raise ValueError
            elif f.type == "real":
                v = float(raw)
            elif f.type == "bool":
                if raw not in (True, False, 0, 1):
                    raise ValueError
                v = int(raw)
            elif f.type == "date":
                v = date.fromisoformat(str(raw)).isoformat()
            elif f.type == "datetime":
                v = datetime.fromisoformat(str(raw)).isoformat()
            else:
                v = str(raw).strip()
                if len(v) > f.max_len:
                    raise ValueError(f"«{f.name}» admite hasta {f.max_len} caracteres")
        except (TypeError, ValueError, OverflowError) as exc:
            msg = str(exc)
            raise ValueError(msg if msg.startswith("«") else f"«{f.name}» no es un valor válido") from None
        if f.choices is not None and v not in f.choices:
            raise ValueError(f"«{f.name}» debe ser uno de: {', '.join(f.choices)}")
        if f.ref:
            target = self._reg.get_entity(f.ref)
            cond = " AND archived = 0" if target.managed else ""
            with self._reg._host.db_lock:
                found = self._reg._host.db.execute(f"SELECT 1 FROM {target.table} WHERE id = ?{cond}", (v,)).fetchone()
            if not found:
                raise ValueError(f"«{f.name}» no existe o está archivado")
        return v

    @staticmethod
    def _translate(exc: sqlite3.IntegrityError) -> ValueError:
        text = str(exc).upper()
        if "FOREIGN KEY" in text:
            return ValueError("la referencia no existe")
        if "UNIQUE" in text:
            return ValueError("ya existe un registro igual")
        return ValueError("no se pudo guardar el registro")

    def create(self, name: str, values: dict, who: str) -> int:
        e = self._entity(name)
        clean = self._clean(e, values, creating=True)
        now = _now()
        cols = [*clean, "created_at", "updated_at", "created_by", "updated_by"]
        with self._reg.transaction():
            try:
                cur = self._reg._host.db.execute(
                    f"INSERT INTO {e.table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    (*clean.values(), now, now, who, who))
            except sqlite3.IntegrityError as exc:
                raise self._translate(exc) from None
            self._reg._queue(name, cur.lastrowid, "create")
        return int(cur.lastrowid)

    def update(self, name: str, id: int, values: dict, who: str) -> None:
        e = self._entity(name)
        check_id(id)
        clean = self._clean(e, values, creating=False)
        sets = [*clean, "updated_at", "updated_by"]
        with self._reg.transaction():
            try:
                cur = self._reg._host.db.execute(
                    f"UPDATE {e.table} SET {', '.join(c + ' = ?' for c in sets)} WHERE id = ?",
                    (*clean.values(), _now(), who, id))
            except sqlite3.IntegrityError as exc:
                raise self._translate(exc) from None
            if cur.rowcount == 0:
                raise ValueError("no existe")
            self._reg._queue(name, id, "update")

    def _set_archived(self, name: str, id: int, who: str, value: int, action: str) -> None:
        e = self._entity(name)
        check_id(id)
        with self._reg.transaction():
            cur = self._reg._host.db.execute(
                f"UPDATE {e.table} SET archived = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                (value, _now(), who, id))
            if cur.rowcount == 0:
                raise ValueError("no existe")
            self._reg._queue(name, id, action)

    def archive(self, name: str, id: int, who: str) -> None:
        self._set_archived(name, id, who, 1, "archive")

    def restore(self, name: str, id: int, who: str) -> None:
        self._set_archived(name, id, who, 0, "restore")


class ReadOnly:
    """Lo que ve un editor o addon (`ctx.entities`): solo lectura."""

    def __init__(self, registry: Registry) -> None:
        self.list, self.get, self.catalog = registry.list, registry.get, registry.catalog


def register_crud(host: "sdk.Host", station: str, names: list[str]) -> None:
    """Registra `<entidad>.crear/.editar/.archivar/.restaurar` (riesgo `datos`) para entidades de `station`."""
    w = host.entities.writer(station)
    for name in names:                          # falla al arrancar, no al ejecutar
        if host.entities.get_entity(name).owner != station:
            raise ValueError(f"«{name}» no es una entidad de {station}")

    def make(name: str) -> None:
        host.register_command(f"{name}.crear", lambda ctx, **campos: w.create(name, campos, who=ctx.principal),
                              risk="datos")
        host.register_command(f"{name}.editar", lambda ctx, id, **campos: w.update(name, id, campos, who=ctx.principal),
                              risk="datos")
        host.register_command(f"{name}.archivar", lambda ctx, id: w.archive(name, id, who=ctx.principal), risk="datos")
        host.register_command(f"{name}.restaurar", lambda ctx, id: w.restore(name, id, who=ctx.principal), risk="datos")

    for name in names:
        host.entities.get_entity(name)
        make(name)


def check_declaration(conn: sqlite3.Connection, entity: Entity) -> list[str]:
    """Diferencias entre la declaración y la tabla real (columnas, REFERENCES y UNIQUE). Lista vacía = coincide."""
    problems: list[str] = []
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({entity.table})")}
    if not cols:
        return [f"la tabla «{entity.table}» no existe"]
    declared = {"id", *(f.name for f in entity.fields)} | (set(STD_COLUMNS) if entity.managed else set())
    for c in sorted(declared - cols):
        problems.append(f"falta la columna «{c}» en «{entity.table}»")
    if entity.managed:
        for c in sorted(cols - declared):
            problems.append(f"la columna «{c}» de «{entity.table}» no está declarada")
    fks = {r["from"] for r in conn.execute(f"PRAGMA foreign_key_list({entity.table})")}
    uniques = set()
    for idx in conn.execute(f"PRAGMA index_list({entity.table})"):
        if idx["unique"]:
            idx_cols = [r["name"] for r in conn.execute(f"PRAGMA index_info({idx['name']})")]
            if len(idx_cols) == 1:
                uniques.add(idx_cols[0])
    for f in entity.fields:
        if f.ref and f.name not in fks:
            problems.append(f"«{f.name}» debería tener REFERENCES en el SQL")
        if f.unique and f.name not in uniques:
            problems.append(f"«{f.name}» debería ser UNIQUE en el SQL")
    return problems
