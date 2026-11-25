"""CLI: `leonradio scan <carpeta>` y `leonradio serve`."""

from __future__ import annotations

import argparse

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
    args = ap.parse_args(argv)
    if args.cmd == "scan":
        conn = db.connect(args.db)
        print(library.scan(conn, args.folder))
    elif args.cmd == "serve":
        from .server import serve
        serve(args.library, args.port)


if __name__ == "__main__":
    main()
