"""The morning / evening digest as text: for the desktop notification and for the Digest button on Today."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from ..application.services import Digest
from .formatting import fmt_min
from .i18n import _


def title(d: Digest) -> str:
    return _("Good morning: your day") if d.morning else _("Good evening: tomorrow and today's ideas")


def lines(d: Digest) -> list[str]:
    out = [f"{fmt_min(m)}  {t}" for m, t in d.items] or [
        _("Nothing planned today") if d.morning else _("Nothing planned tomorrow")]
    out += [_("To do: {task}").format(task=t) for t in d.due]
    if d.overdue:
        out.append(_("{n} late: just start one").format(n=d.overdue))
    out += [_("Idea: {idea}").format(idea=i) for i in d.ideas]
    return out


class DigestDialog(QDialog):
    """The digest right now, any time of day."""

    def __init__(self, d: Digest, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title(d))
        layout = QVBoxLayout(self)
        for line in lines(d):
            text = QLabel(line, wordWrap=True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(text)
        layout.addStretch(1)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)
        self.setMinimumWidth(420)
