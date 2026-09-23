"""Build a standalone Quire app for the current platform.

    python scripts/build.py            # folder build in dist/Quire/
    python scripts/build.py --onefile  # single executable
    python scripts/build.py --deb      # Debian/Ubuntu package in dist/

Run it on Linux to get a Linux build and on Windows to get a Windows .exe;
PyInstaller does not cross-compile.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import quire  # noqa: E402  (release metadata only; no Qt imports)

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


def write_windows_version_file() -> Path:
    """File properties shown in Windows Explorer (Details tab) for Quire.exe."""
    parts = [int(p) for p in quire.__version__.split(".")]
    nums = tuple(parts + [0] * (4 - len(parts)))
    strings = {
        "CompanyName": quire.DEVELOPER,
        "FileDescription": f"{quire.APP_NAME}: notes, day planner and school timetable",
        "FileVersion": quire.__version__,
        "InternalName": quire.APP_NAME,
        "LegalCopyright": f"Copyright (c) {date.today().year} {quire.DEVELOPER}",
        "OriginalFilename": f"{quire.APP_NAME}.exe",
        "ProductName": quire.APP_NAME,
        "ProductVersion": quire.__version__,
    }
    entries = ",\n          ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    BUILD.mkdir(exist_ok=True)
    target = BUILD / "windows-version.txt"
    target.write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0,
                    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
          {entries}])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])]),
  ],
)
""", encoding="utf-8")
    return target


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--onefile", action="store_true", help="single self-contained executable")
    mode.add_argument("--deb", action="store_true", help="installable .deb (Linux only)")
    args = parser.parse_args()
    if args.deb and not sys.platform.startswith("linux"):
        parser.error("--deb can only be built on Linux")

    import PyInstaller.__main__

    icon = render_icons()
    windows_only = (["--version-file", str(write_windows_version_file())]
                    if sys.platform == "win32" else [])
    PyInstaller.__main__.run([
        *windows_only,
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
    if args.deb:
        from deb import build_deb

        deb = build_deb(ROOT / "dist" / "Quire", icon, ROOT / "dist", BUILD)
        print(f"\nPackage: {deb}\nInstall with: sudo apt install {deb}")
    else:
        print(f"\nBuilt into {ROOT / 'dist'}")


if __name__ == "__main__":
    main()
