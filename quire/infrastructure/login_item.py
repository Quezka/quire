"""Starting Quire when you log in.

Linux: an XDG autostart entry in ~/.config/autostart. Windows: the per-user Run key.
Both start Quire with --background, so it goes straight to the tray.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .. import APP_ID

BACKGROUND_FLAG = "--background"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "Quire"


def launch_command(frozen: bool | None = None, executable: str | None = None) -> list[str]:
    """How to start this copy of Quire in the background."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    executable = executable or sys.executable
    if frozen:  # the .deb or the Windows installer
        return [executable, BACKGROUND_FLAG]
    python = executable
    if sys.platform == "win32":  # no console window at login
        python = str(Path(python).with_name("pythonw.exe"))
    return [python, "-m", "quire", BACKGROUND_FLAG]


def desktop_exec(args: list[str]) -> str:
    """Quote arguments for a .desktop Exec= line (Desktop Entry spec)."""
    def quote(arg: str) -> str:
        if arg and not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
            return arg
        return '"' + "".join("\\" + c if c in '"`$\\' else c for c in arg) + '"'
    return " ".join(quote(a) for a in args)


class XdgAutostart:
    def __init__(self, config_dir: Path | None = None, command: list[str] | None = None):
        base = config_dir or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
        self.path = base / "autostart" / f"{APP_ID}.desktop"
        self._command = command

    def supported(self) -> bool:
        return True

    def enabled(self) -> bool:
        return self.path.exists()

    def set_enabled(self, on: bool) -> None:
        if not on:
            self.path.unlink(missing_ok=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=Quire\n"
            "Comment=Start Quire in the background\n"
            f"Exec={desktop_exec(self._command or launch_command())}\n"
            f"Icon={APP_ID}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n", encoding="utf-8")


class WindowsRunKey:
    def __init__(self, command: list[str] | None = None):
        self._command = command

    def supported(self) -> bool:
        return True

    def enabled(self) -> bool:
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                winreg.QueryValueEx(key, RUN_VALUE)
            return True
        except OSError:
            return False

    def set_enabled(self, on: bool) -> None:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ,
                                  subprocess.list2cmdline(self._command or launch_command()))
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass


class NoLoginItem:
    def supported(self) -> bool:
        return False

    def enabled(self) -> bool:
        return False

    def set_enabled(self, on: bool) -> None:
        raise OSError(0, "unsupported")


def platform_login_item():
    if sys.platform == "win32":
        return WindowsRunKey()
    if sys.platform.startswith("linux"):
        return XdgAutostart()
    return NoLoginItem()
