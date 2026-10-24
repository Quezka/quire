"""Do Not Disturb switches for the desktop Quire runs on."""
from __future__ import annotations

import os
import shutil
import subprocess

SCHEMA = "org.gnome.desktop.notifications"


class NoQuiet:
    """No way to silence this desktop from Quire (Windows, KDE and others for now)."""

    name = ""

    def available(self) -> bool:
        return False

    def set_quiet(self, on: bool) -> None:
        pass


class GnomeQuiet:
    """GNOME (Ubuntu): turn the notification banners and their sounds off, remembering what
    they were so they come back as they were."""

    name = "GNOME"

    def __init__(self, runner=subprocess.run):
        self._run = runner
        self._before: str | None = None

    def _gsettings(self, *args: str) -> str:
        return self._run(["gsettings", *args], capture_output=True, text=True, timeout=5).stdout.strip()

    def available(self) -> bool:
        return shutil.which("gsettings") is not None

    def set_quiet(self, on: bool) -> None:
        if on:
            self._before = self._gsettings("get", SCHEMA, "show-banners") or "true"
            self._gsettings("set", SCHEMA, "show-banners", "false")
        else:
            self._gsettings("set", SCHEMA, "show-banners", self._before or "true")
            self._before = None


def platform_quiet():
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if os.name == "posix" and ("gnome" in desktop or "ubuntu" in desktop):
        return GnomeQuiet()
    return NoQuiet()
