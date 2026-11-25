"""CLI mínima: `leonradio scan <carpeta> [--db leonradio.db]`."""

from __future__ import annotations

import argparse

from . import db, library


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="leonradio")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="escanear una carpeta de emisora")
    sc.add_argument("folder")
    sc.add_argument("--db", default="leonradio.db")
    args = ap.parse_args(argv)
    if args.cmd == "scan":
        conn = db.connect(args.db)
        print(library.scan(conn, args.folder))


if __name__ == "__main__":
    main()
