"""Sleep, Water and Medicines on one sidebar entry (0.52: fewer entries, less crowded), switched on top."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from quezka_ui.widgets import Segmented

from ..i18n import _


class HealthView(QWidget):
    switched = Signal(object)

    def __init__(self, sleep, water, medicine, parent=None):
        super().__init__(parent)
        self.pages = {"sleep": sleep, "water": water, "medicine": medicine}
        self.switch = Segmented([("sleep", _("Sleep")), ("water", _("Water")), ("medicine", _("Medicines"))])
        self.stack = QStackedWidget()
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.switch.changed.connect(self.show_part)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.switch, 0, Qt.AlignHCenter)
        layout.addWidget(self.stack, 1)
        self.show_part("sleep")

    def show_part(self, part: str):
        self.switch.set_value(part)
        self.stack.setCurrentWidget(self.pages[part])
        self.switched.emit(part)

    def current(self):
        return self.stack.currentWidget()
