"""Desktop notifications: notify-send on Linux, the tray balloon elsewhere."""
from __future__ import annotations

import shutil
import subprocess
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from .. import APP_ID
from .icons import APP_ICON

_tray: QSystemTrayIcon | None = None


def notify(title: str, body: str) -> None:
    if sys.platform.startswith("linux") and shutil.which("notify-send"):
        try:
            subprocess.Popen(["notify-send", "--app-name=Quire", f"--icon={APP_ID}", title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    global _tray
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return
    if _tray is None:
        _tray = QSystemTrayIcon(QIcon(str(APP_ICON)), QApplication.instance())
        _tray.setToolTip("Quire")
        _tray.show()
    _tray.showMessage(title, body, QIcon(str(APP_ICON)), 8000)
