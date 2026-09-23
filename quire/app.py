"""Command-line entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bootstrap import build_services
from .infrastructure.paths import data_dir


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    parser = argparse.ArgumentParser(prog="quire", description="Notes, planner and timetable.")
    parser.add_argument("--db", type=Path, help="use this database file instead of the default")
    parser.add_argument("--demo", action="store_true",
                        help="open a throwaway database filled with sample data")
    args, qt_args = parser.parse_known_args(argv[1:])

    if args.demo and args.db:
        parser.error("--demo always uses its own throwaway database; drop --db")
    if args.demo:
        path = data_dir() / "demo.db"
        path.unlink(missing_ok=True)
    else:
        path = args.db or data_dir() / "quire.db"
    if args.demo:
        from datetime import date

        from .demo import DemoRegister, seed, seed_school
        from .infrastructure.credentials import MemoryCredentialStore

        services, db = build_services(path, register=DemoRegister(date.today()),
                                      credentials=MemoryCredentialStore())
        seed(services)
        seed_school(services)
    else:
        services, db = build_services(path)

    # Imported late so `--help` works without a display.
    from .presentation.qt_app import run

    try:
        return run(services, [argv[0], *qt_args])
    finally:
        db.close()
