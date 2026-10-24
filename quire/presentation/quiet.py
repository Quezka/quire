"""Keeps the computer's Do Not Disturb in step with what is on, while Quire is open."""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer

from ..application.services import Services


class QuietRunner(QObject):
    INTERVAL_MS = 30_000

    def __init__(self, services: Services, parent=None):
        super().__init__(parent)
        self.service = services.quiet
        self.timer = QTimer(self, interval=self.INTERVAL_MS)
        self.timer.timeout.connect(self.service.tick)
        self.timer.start()
        QTimer.singleShot(1000, self.service.tick)
