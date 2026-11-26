"""Estaciones de trabajo de LeonRadio (ver docs/estaciones.md y docs/guia-basica.md).

Una estación es un módulo con SUS paneles y comandos; todas comparten el núcleo (datos, usuarios, permisos) y los
paneles comunes. Cada carpeta define `register(host)`; `register_all` las carga al arrancar. Quien lleve una estación
trabaja dentro de su carpeta y no toca los archivos de las otras: así los PR no chocan.
"""

from __future__ import annotations

import importlib

from .. import sdk

# Datos de cada estación (alcance según «Arquitectura Leon Radio»). `tareas`: ids del docs/ROADMAP.md.
STATIONS: dict[str, dict] = {
    "al_aire": {
        "nombre": "Al Aire", "estado": "en desarrollo",
        "alcance": ["Emisión y controles", "Escaleta y guiones", "Invitados", "Comunicación interna", "Participación de la audiencia"],
        "tareas": ["S2", "S3", "S4", "A8", "B6", "C3", "C4"],
    },
    "programacion": {
        "nombre": "Programación", "estado": "en construcción",
        "alcance": ["Parrilla y relojes", "Librería, artistas, álbumes y géneros", "Fórmulas y rotaciones", "Automatización y continuidad"],
        "tareas": ["A1", "A2", "A3", "A4", "A5", "A7"],
    },
    "direccion": {
        "nombre": "Dirección", "estado": "por iniciar",
        "alcance": ["Identidad de programas", "Línea artística y formatos", "Guías de estilo", "Dirección de talento", "Estrategia transmedia"],
        "tareas": ["B3"],
    },
    "produccion": {
        "nombre": "Producción", "estado": "por iniciar",
        "alcance": ["Presupuestos e inventario", "Contratos, patrocinios y pauta", "Facturación y cronogramas", "Informes y administración"],
        "tareas": ["A6", "B1", "B2"],
    },
}


def register_all(host: sdk.Host) -> None:
    """Carga el módulo de cada estación. Un fallo en una no impide arrancar las demás."""
    sdk.bind(host)
    for key in STATIONS:
        try:
            importlib.import_module(f"{__name__}.{key}").register(host)
        except Exception:  # noqa: BLE001
            sdk.log.exception("la estación %s no pudo registrarse", key)
