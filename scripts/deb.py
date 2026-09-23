"""Wrap a PyInstaller folder build of Quire into an installable .deb.

Layout inside the package:
    /opt/quire/                         the frozen app (binary + bundled Qt/Python)
    /usr/bin/quire                      symlink to /opt/quire/Quire
    /usr/share/applications/quire.desktop
    /usr/share/icons/hicolor/...        scalable SVG + 256px PNG

The desktop database and icon cache refresh through dpkg triggers, so no
maintainer scripts are needed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Bundled Qt still links against these system libraries.
DEPENDS = [
    "libc6",
    "libegl1",
    "libgl1",
    "libfontconfig1",
    "libfreetype6",
    "libxkbcommon0",
    "libxkbcommon-x11-0",
    "libxcb-cursor0",
    "libdbus-1-3",
    "libglib2.0-0t64 | libglib2.0-0",
]


def _version() -> str:
    namespace: dict = {}
    exec((ROOT / "quire" / "__init__.py").read_text(), namespace)
    return namespace["__version__"]


def _architecture() -> str:
    return subprocess.run(["dpkg", "--print-architecture"], check=True,
                          capture_output=True, text=True).stdout.strip()


def _installed_size_kib(root: Path) -> int:
    total = sum(p.lstat().st_size for p in root.rglob("*") if not p.is_dir())
    return (total + 1023) // 1024


def build_deb(app_dir: Path, png_icon: Path, out_dir: Path, work_dir: Path) -> Path:
    if shutil.which("dpkg-deb") is None:
        raise SystemExit("dpkg-deb not found; build the .deb on a Debian/Ubuntu system")
    version, arch = _version(), _architecture()
    stage = work_dir / "deb-root"
    shutil.rmtree(stage, ignore_errors=True)

    opt = stage / "opt" / "quire"
    shutil.copytree(app_dir, opt, symlinks=True)

    bin_dir = stage / "usr" / "bin"
    bin_dir.mkdir(parents=True)
    os.symlink("/opt/quire/Quire", bin_dir / "quire")

    share = stage / "usr" / "share"
    (share / "applications").mkdir(parents=True)
    shutil.copy(ROOT / "packaging" / "quire.desktop", share / "applications" / "quire.desktop")
    icons = share / "icons" / "hicolor"
    (icons / "scalable" / "apps").mkdir(parents=True)
    shutil.copy(ROOT / "quire" / "assets" / "icon.svg", icons / "scalable" / "apps" / "quire.svg")
    (icons / "256x256" / "apps").mkdir(parents=True)
    shutil.copy(png_icon, icons / "256x256" / "apps" / "quire.png")

    for path in stage.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir() or os.access(path, os.X_OK):
            path.chmod(0o755)
        else:
            path.chmod(0o644)

    debian = stage / "DEBIAN"
    debian.mkdir()
    (debian / "control").write_text(
        f"Package: quire\n"
        f"Version: {version}\n"
        f"Architecture: {arch}\n"
        f"Maintainer: quezka <arsdom15@gmail.com>\n"
        f"Installed-Size: {_installed_size_kib(stage)}\n"
        f"Depends: {', '.join(DEPENDS)}\n"
        f"Section: utils\n"
        f"Priority: optional\n"
        f"Homepage: https://github.com/Quezka/quire\n"
        f"Description: Notes, day planner and school timetable\n"
        f" Quire keeps your weekly school timetable, a day planner, homework and\n"
        f" exams, and markdown notes in one desktop app. Data is stored locally\n"
        f" in a single SQLite file.\n"
    )
    debian.chmod(0o755)
    (debian / "control").chmod(0o644)

    out_dir.mkdir(parents=True, exist_ok=True)
    deb = out_dir / f"quire_{version}_{arch}.deb"
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(stage), str(deb)],
                   check=True)
    return deb
