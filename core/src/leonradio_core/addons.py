"""Carga de addons: manifiesto `leonradio_addon.toml` + módulo Python con register()/unregister().

NOTA v0: los addons se cargan en el MISMO proceso, con permisos comprobados en la API.
El aislamiento en proceso aparte (para proteger la emisión) está pendiente (ver ROADMAP).
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from . import sdk

log = logging.getLogger("leonradio.addons")
MANIFEST = "leonradio_addon.toml"


class AddonError(Exception):
    pass


@dataclass
class Manifest:
    id: str
    name: str
    version: str
    api_version: str
    license: str
    permissions: frozenset[str]
    path: Path


def read_manifest(folder: Path) -> Manifest:
    mf = folder / MANIFEST
    if not mf.is_file():
        raise AddonError(f"{folder.name}: falta {MANIFEST}")
    data = tomllib.loads(mf.read_text(encoding="utf-8"))
    for key in ("id", "name", "version", "api_version"):
        if not data.get(key):
            raise AddonError(f"{folder.name}: manifiesto sin '{key}'")
    perms = frozenset(data.get("permissions", []))
    unknown = perms - sdk.PERMISSIONS
    if unknown:
        raise AddonError(f"{data['id']}: permisos desconocidos {sorted(unknown)}")
    if data["api_version"].split(".")[0:2] != sdk.API_VERSION.split(".")[0:2]:
        raise AddonError(f"{data['id']}: api_version {data['api_version']} incompatible con {sdk.API_VERSION}")
    return Manifest(data["id"], data["name"], data["version"], data["api_version"],
                    data.get("license", ""), perms, folder)


def load_addon(host: sdk.Host, folder: Path, approved: set[str] | None = None) -> Manifest:
    """Carga un addon. `approved`: permisos que el usuario aprobó (None = los que pide)."""
    m = read_manifest(folder)
    granted = m.permissions if approved is None else (m.permissions & approved)
    if m.permissions - granted:
        log.warning("%s: permisos NO aprobados: %s", m.id, sorted(m.permissions - granted))
    init = folder / "__init__.py"
    if not init.is_file():
        raise AddonError(f"{m.id}: falta __init__.py")
    modname = f"leonradio_addon_{m.id.replace('.', '_').replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(modname, init, submodule_search_locations=[str(folder)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[modname] = module
    sdk.bind(host, m.id, frozenset(granted))
    try:
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        if hasattr(module, "register"):
            module.register()
    except Exception as exc:
        host.unregister_owner(m.id)
        sys.modules.pop(modname, None)
        raise AddonError(f"{m.id}: falló al cargar: {exc}") from exc
    finally:
        sdk.bind(host)  # vuelve al dueño «builtin»
    log.info("addon cargado: %s %s", m.id, m.version)
    return m


def discover(host: sdk.Host, *roots: Path) -> list[Manifest]:
    loaded: list[Manifest] = []
    for root in roots:
        if not root.is_dir():
            continue
        for folder in sorted(p for p in root.iterdir() if (p / MANIFEST).is_file()):
            try:
                loaded.append(load_addon(host, folder))
            except AddonError as exc:  # un addon roto no impide arrancar
                log.error("%s", exc)
    return loaded
