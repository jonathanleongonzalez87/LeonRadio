"""CLI: `leonradio scan`, `serve`, `devices` y `beep`."""

from __future__ import annotations

import argparse
import os

from . import db, library


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="leonradio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="escanear una carpeta de emisora")
    sc.add_argument("folder")
    sc.add_argument("--db", default="leonradio.db")

    sv = sub.add_parser("serve", help="iniciar servidor + UI (http://127.0.0.1:8765)")
    sv.add_argument("--library", help="carpeta de la emisora (música, jingles…)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--host", default=None,
                    help="127.0.0.1 = solo este equipo (por defecto); 0.0.0.0 = también otros equipos de la red local")
    sv.add_argument("--audio", choices=["device", "null"], default="device",
                    help="device = salida real (WASAPI); null = simulado, sin sonido")
    sv.add_argument("--device", help="número o parte del nombre del dispositivo de salida (ver `leonradio devices`)")
    sv.add_argument("--autoplay", action="store_true",
                    help="empezar a sonar al arrancar (por defecto la emisión empieza en pausa)")

    sub.add_parser("devices", help="listar los dispositivos de salida de audio")
    bp = sub.add_parser("beep", help="probar la salida: tono por el canal izquierdo y luego el derecho")
    bp.add_argument("--device")

    args = ap.parse_args(argv)
    if args.cmd == "scan":
        conn = db.connect(args.db)
        print(library.scan(conn, args.folder))
    elif args.cmd == "serve":
        from .server import serve
        autoplay = args.autoplay or os.environ.get("LEONRADIO_AUTOPLAY") == "1"
        serve(args.library, args.port, args.audio, args.device or os.environ.get("LEONRADIO_DEVICE"),
              True if autoplay else None, args.host or os.environ.get("LEONRADIO_HOST") or "127.0.0.1")
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
