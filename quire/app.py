"""Command-line entry point."""
from __future__ import annotations

import argparse
import os
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
    parser.add_argument("--background", action="store_true",
                        help="start in the tray without opening the window (used at login)")
    parser.add_argument("--no-splash", action="store_true",
                        help="don't show the start-up splash screen (QUIRE_NO_SPLASH=1 does too)")
    args, qt_args = parser.parse_known_args(argv[1:])

    if args.demo and args.db:
        parser.error("--demo always uses its own throwaway database; drop --db")
    if args.demo:
        path = data_dir() / "demo.db"
        path.unlink(missing_ok=True)
    else:
        path = args.db or data_dir() / "quire.db"
    # The splash goes up before the database is opened, so it covers the slow part of starting.
    app = splash = None
    if not (args.background or args.no_splash or os.environ.get("QUIRE_NO_SPLASH")):
        from . import __version__
        from .presentation.i18n import _
        from .presentation.qt_app import create_application
        from .presentation.splash import SplashScreen

        app = create_application([argv[0], *qt_args])
        splash = SplashScreen(__version__)
        splash.show()
        splash.step(_("Starting…"), 0.12)
        splash.step(_("Opening your data…"), 0.35)
    if args.demo:
        from datetime import date

        from .demo import seed, seed_school
        from .infrastructure.demo_register import DemoRegister
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
        return run(services, [argv[0], *qt_args], background=args.background, app=app,
                   splash=splash)
    finally:
        db.close()
