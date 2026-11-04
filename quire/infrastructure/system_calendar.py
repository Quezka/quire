"""The computer's own calendar. On Linux, GNOME Calendar and Evolution read Evolution Data Server's sources, and a
"local" source can point at a file it keeps following: a read-only calendar that changes as the file does. Windows
has no such thing for a local file, so there the file is handed to the calendar app, which imports it."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Quire"
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "Quire"


def _config_dir() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


class _FileCalendar:
    def __init__(self, folder: Path | None = None):
        self.file = (folder or _data_dir()) / "agenda.ics"

    def publish(self, text: str) -> None:
        data = text.encode("utf-8")  # bytes: iCalendar lines end in CRLF, and text mode would change them
        try:
            if self.file.is_file() and self.file.read_bytes() == data:
                return  # nothing new: a calendar watching the file needn't reload
        except OSError:
            pass
        self.file.parent.mkdir(parents=True, exist_ok=True)
        partial = self.file.with_name(self.file.name + ".part")
        partial.write_bytes(data)
        partial.chmod(0o600)
        partial.replace(self.file)

    def open(self) -> None:
        if sys.platform == "win32":
            os.startfile(self.file)  # noqa: S606 (our own file, the system's handler for .ics)
        else:
            subprocess.Popen(["xdg-open", str(self.file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class EvolutionCalendar(_FileCalendar):
    """A source file for Evolution Data Server, which picks it up by itself and shows it in GNOME Calendar."""

    SOURCE = "quire-agenda.source"

    def __init__(self, folder: Path | None = None, sources: Path | None = None):
        super().__init__(folder)
        self.sources = sources or _config_dir() / "evolution" / "sources"

    def can_subscribe(self) -> bool:
        return True

    def connect(self) -> None:
        self.sources.mkdir(parents=True, exist_ok=True)
        (self.sources / self.SOURCE).write_text(
            "[Data Source]\nDisplayName=Quire\nEnabled=true\nParent=local-stub\n\n"
            "[Calendar]\nBackendName=local\nColor=#5b5bd6\nSelected=true\n\n"
            f"[Local Backend]\nCustomFile=file://{self.file}\nWritable=false\n", encoding="utf-8")

    def disconnect(self) -> None:
        (self.sources / self.SOURCE).unlink(missing_ok=True)


class WindowsCalendar(_FileCalendar):
    def can_subscribe(self) -> bool:
        return False

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass


def platform_calendar():
    return WindowsCalendar() if sys.platform == "win32" else EvolutionCalendar()
