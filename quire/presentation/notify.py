"""Desktop notifications: notify-send on Linux, the tray balloon elsewhere.

Each one comes with Quire's own chime (assets/chime.wav, the same as on Android), unless
it's turned off in Settings. On Linux the notification server plays it when it can, so
Do Not Disturb silences it too; otherwise Quire plays it itself.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_ID
from .icons import APP_ICON
from .i18n import _
from .preferences import preferences

CHIME = APP_ICON.with_name("chime.wav")
PLAYERS = (["pw-play"], ["paplay"], ["aplay", "-q"])  # PipeWire, PulseAudio, plain ALSA

_tray: QSystemTrayIcon | None = None
_server_plays_sounds: bool | None = None


def notify(title: str, body: str) -> None:
    sound = preferences().notification_sound()
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "--app-name=Quire", f"--icon={APP_ID}",
                              *sound_hints(sound, server_plays_sounds()), title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if sound and not server_plays_sounds():
                play_chime()
            return
        except OSError:
            pass
    global _tray
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    if _tray is None:
        _tray = QSystemTrayIcon(QIcon(str(APP_ICON)), QApplication.instance())
        _tray.setToolTip(_("Quire"))
        _tray.show()
    _tray.showMessage(title, body, QIcon(str(APP_ICON)), 8000)
    if sound:
        play_chime()


def sound_hints(sound: bool, server_plays: bool, chime: Path = CHIME) -> list[str]:
    """notify-send hints: the chime for a server that plays sounds, else silence its own."""
    if sound and server_plays:
        return [f"--hint=string:sound-file:{chime}", "--hint=boolean:suppress-sound:false"]
    return ["--hint=boolean:suppress-sound:true"]


def server_plays_sounds() -> bool:
    """Whether the desktop's notification server advertises the "sound" capability."""
    global _server_plays_sounds
    if _server_plays_sounds is None:
        _server_plays_sounds = False
        if shutil.which("gdbus"):
            try:
                out = subprocess.run(
                    ["gdbus", "call", "--session", "--dest", "org.freedesktop.Notifications",
                     "--object-path", "/org/freedesktop/Notifications",
                     "--method", "org.freedesktop.Notifications.GetCapabilities"],
                    capture_output=True, text=True, timeout=2).stdout
                _server_plays_sounds = "'sound'" in out
            except (OSError, subprocess.SubprocessError):
                pass
    return _server_plays_sounds


def play_chime() -> None:
    """Play the chime without waiting for it (Settings uses this for "Play")."""
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(str(CHIME), winsound.SND_FILENAME | winsound.SND_ASYNC
                           | winsound.SND_NODEFAULT)
        return
    for player in PLAYERS:
        if shutil.which(player[0]):
            try:
                subprocess.Popen([*player, str(CHIME)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except OSError:
                continue
