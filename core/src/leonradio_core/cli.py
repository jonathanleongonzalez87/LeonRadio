"""CLI: `leonradio scan`, `serve`, `clave`, `carpetas`, `devices` y `beep`."""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

from . import auth, db, library, paths, settings


def _carpetas(args: argparse.Namespace) -> None:
    current = settings.get_allowed_paths()
    if args.agregar:
        try:
            p = str(paths.validate_new_root(args.agregar))
        except ValueError as exc:
            raise SystemExit(f"\nNo se agregó: {exc}.\n")
        if p not in current:
            settings.set_allowed_paths([*current, p])
        print(f"\nCarpeta permitida: {p}\n(Si LeonRadio está abierto, recarga la página para verla en el Explorador.)\n")
    elif args.quitar:
        try:
            target = str(Path(args.quitar).resolve())
        except OSError:
            target = args.quitar
        keep = [p for p in current if p != target and p != args.quitar]
        if len(keep) == len(current):
            raise SystemExit("\nEsa carpeta no está en la lista de agregadas.\n")
        settings.set_allowed_paths(keep)
        print(f"\nYa no se permite: {target}\n")
    else:
        print("\nCarpetas permitidas (además de la biblioteca de la emisora, si la hay):")
        for name, p in paths.places(None):
            print(f"  · {name}: {p}")
        print()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="leonradio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="escanear una carpeta de emisora")
    sc.add_argument("folder")
    sc.add_argument("--db", default=None, help="archivo de la base (por defecto LEONRADIO_DB o la carpeta del usuario)")

    sv = sub.add_parser("serve", help="iniciar servidor + UI (http://127.0.0.1:8765)")
    sv.add_argument("--library", help="carpeta de la emisora (música, jingles…)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--host", default=None,
                    help="127.0.0.1 = solo este equipo (por defecto); 0.0.0.0 = también otros equipos de la red local")
    sv.add_argument("--audio", choices=["device", "null"], default="device",
                    help="device = salida real (WASAPI); null = simulado, sin sonido")
    sv.add_argument("--device", help="número o parte del nombre del dispositivo de salida (ver `leonradio devices`)")
    sv.add_argument("--db", default=None, help="archivo de la base (por defecto LEONRADIO_DB o la carpeta del usuario)")
    sv.add_argument("--autoplay", action="store_true",
                    help="empezar a sonar al arrancar (por defecto la emisión empieza en pausa)")

    sub.add_parser("clave", help="crear una clave de acceso nueva para el modo red (la anterior deja de valer)")
    cp = sub.add_parser("carpetas", help="carpetas que el navegador puede abrir (además de la biblioteca, Música, Descargas y Escritorio)")
    g = cp.add_mutually_exclusive_group()
    g.add_argument("--agregar", metavar="RUTA", help="permitir una carpeta")
    g.add_argument("--quitar", metavar="RUTA", help="dejar de permitir una carpeta agregada")
    g.add_argument("--lista", action="store_true", help="mostrar las carpetas permitidas (por defecto)")

    sub.add_parser("devices", help="listar los dispositivos de salida de audio")
    bp = sub.add_parser("beep", help="probar la salida: tono por el canal izquierdo y luego el derecho")
    bp.add_argument("--device")

    args = ap.parse_args(argv)
    if args.cmd == "scan":
        try:
            conn = db.connect(settings.db_path(args.db))
        except RuntimeError as exc:
            raise SystemExit(f"\nERROR: {exc}\n")
        except sqlite3.DatabaseError as exc:
            raise SystemExit(f"\nERROR: no se pudo abrir la base de datos ({exc}). Restaura una copia de la carpeta «copias» "
                             "(ver docs/arquitectura.md) o usa otra base con --db.\n")
        print(library.scan(conn, args.folder))
        db.close(conn)
    elif args.cmd == "serve":
        from .server import serve
        autoplay = args.autoplay or os.environ.get("LEONRADIO_AUTOPLAY") == "1"
        serve(args.library, args.port, args.audio, args.device or os.environ.get("LEONRADIO_DEVICE"),
              True if autoplay else None, args.host or os.environ.get("LEONRADIO_HOST") or "127.0.0.1", args.db)
    elif args.cmd == "clave":
        key = auth.rotate()
        print(f"\nClave de acceso nueva:  {key}\n\nAnótala: no se vuelve a mostrar. "
              "Las sesiones abiertas y la clave anterior dejan de valer.\n")
    elif args.cmd == "carpetas":
        _carpetas(args)
    elif args.cmd == "devices":
        from .engine.output import list_devices
        for d in list_devices():
            mark = " <- por defecto" if d["is_default"] else ""
            print(f"[{d['index']:>2}] {d['name']}  ({d['hostapi']}, {d['channels']} canales){mark}")
    elif args.cmd == "beep":
        from .engine.output import beep
        print("Sonará un tono de 440 Hz: 1 s por el izquierdo y 1 s por el derecho…")
        print("Dispositivo:", beep(args.device))


if __name__ == "__main__":
    main()
