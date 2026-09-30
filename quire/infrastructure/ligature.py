"""Ligature (https://github.com/Quezka/ligature), the diagram app, as the editor for diagram
pictures in notes.

Ligature's PNG exports carry the diagram in a compressed `zTXt` chunk with the keyword
`ligature`; opened in Ligature, such a picture is edited and saved back into the same file.
"""
from __future__ import annotations

import errno
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .paths import data_dir

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
KEYWORD = b"ligature\0"


def has_diagram(png: bytes) -> bool:
    if not png.startswith(PNG_SIGNATURE):
        return False
    pos = len(PNG_SIGNATURE)
    while pos + 8 <= len(png):
        length, kind = struct.unpack(">I4s", png[pos:pos + 8])
        if kind == b"zTXt" and png[pos + 8:pos + 8 + len(KEYWORD)] == KEYWORD:
            return True
        if kind == b"IEND":
            return False
        pos += 12 + length
    return False


def find_ligature() -> str | None:
    found = shutil.which("ligature")
    if found or sys.platform != "win32":
        return found
    import winreg  # its installer registers an "App Paths" entry
    key = r"Software\Microsoft\Windows\CurrentVersion\App Paths\Ligature.exe"
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, key) as k:
                path = winreg.QueryValue(k, None)
        except OSError:
            continue
        if path and Path(path).is_file():
            return path
    return None


class LigatureApp:
    def __init__(self, folder: Path | None = None, finder: Callable[[], str | None] = find_ligature,
                 launcher: Callable = subprocess.Popen):
        self._folder = folder
        self._find = finder
        self._launch = launcher

    def available(self) -> bool:
        return self._find() is not None

    def is_diagram(self, data: bytes) -> bool:
        return has_diagram(data)

    def open(self, name: str, data: bytes) -> str:
        folder = self._folder or data_dir() / "diagrams"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_bytes(data)
        exe = self._find()
        if exe is None:
            raise FileNotFoundError(errno.ENOENT, "Ligature is not installed")
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        self._launch([exe, str(path)], creationflags=flags, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL)
        return str(path)

    def read(self, path: str) -> bytes | None:
        try:
            return Path(path).read_bytes()
        except OSError:
            return None
