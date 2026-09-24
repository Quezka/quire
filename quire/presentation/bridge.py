"""Adapts the framework-free ChangeBus to a Qt signal."""
from PySide6.QtCore import QObject, Signal

from ..application.bus import ChangeBus


class ChangeRelay(QObject):
    changed = Signal(object)  # application.bus.Topic

    def __init__(self, bus: ChangeBus, parent=None):
        super().__init__(parent)
        unsubscribe = bus.subscribe(self.changed.emit)
        self.destroyed.connect(lambda *_args: unsubscribe())
