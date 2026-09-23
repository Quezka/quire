"""Build a standalone Quire app for the current platform.

    python scripts/build.py            # folder build in dist/Quire/
    python scripts/build.py --onefile  # single executable

Run it on Linux to get a Linux build and on Windows to get a Windows .exe;
PyInstaller does not cross-compile.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "quire" / "assets"
BUILD = ROOT / "build"


def render_icons() -> Path:
    """Rasterise the SVG icon into the format this platform's executable wants."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 (keeps Qt alive)
    renderer = QSvgRenderer(str(ASSETS / "icon.svg"))
    image = QImage(256, 256, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    BUILD.mkdir(exist_ok=True)
    target = BUILD / ("quire.ico" if sys.platform == "win32" else "quire.png")
    if not image.save(str(target)):
        raise SystemExit(f"could not write {target}")
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true")
    args = parser.parse_args()

    import PyInstaller.__main__

    icon = render_icons()
    PyInstaller.__main__.run([
        str(ROOT / "scripts" / "launcher.py"),
        "--name", "Quire",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--onefile" if args.onefile else "--onedir",
        "--icon", str(icon),
        "--add-data", f"{ASSETS}{os.pathsep}quire/assets",
        "--paths", str(ROOT),
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
        # Trim Qt modules Quire never uses.
        "--exclude-module", "PySide6.QtWebEngineCore",
        "--exclude-module", "PySide6.QtQml",
        "--exclude-module", "PySide6.QtQuick",
        "--exclude-module", "PySide6.Qt3DCore",
        "--exclude-module", "PySide6.QtMultimedia",
        "--exclude-module", "tkinter",
    ])
    print(f"\nBuilt into {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
