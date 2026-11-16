"""Today's Inbox: ideas waiting for a decision, newest first. One click each: make it a task for today,
or mark it done (with Undo). Replaces the old Day notes card."""
from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QWidget

from ...application.services import Services
from ..i18n import _
from .common import Card, badge, icon_button

SHOWN = 4  # more -> "N more in Ideas" <- card stays short (1366x768)


class InboxCard(Card):
    openIdeas = Signal()

    def __init__(self, services: Services, day=None, parent=None):
        super().__init__(_("Inbox"), parent=parent)
        self.services = services
        self._day = day or services.planner.today
        self.count = badge()
        self.title_row.insertWidget(1, self.count)
        self._rows: list[QWidget] = []
        self._undo_record = None
        self.empty = QLabel(_("Inbox empty. Ideas you catch (Ctrl+I) land here."), objectName="hint")
        self.empty.setWordWrap(True)
        self.body.addWidget(self.empty)
        self.more = QPushButton()
        self.more.setCursor(Qt.PointingHandCursor)
        self.more.clicked.connect(self.openIdeas.emit)
        self.undo_row = QWidget()
        undo = QHBoxLayout(self.undo_row)
        undo.setContentsMargins(0, 0, 0, 0)
        self.undo_text = QLabel(objectName="hint")
        self.undo_btn = QPushButton(_("Undo"))
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self._undo)
        undo.addWidget(self.undo_text, 1)
        undo.addWidget(self.undo_btn)
        self.body.addWidget(self.more)
        self.body.addWidget(self.undo_row)
        self.undo_row.hide()
        self.refresh()

    def refresh(self):
        for row in self._rows:
            row.deleteLater()
        self._rows = []
        ideas = self.services.ideas.ideas(include_done=False)
        ideas.sort(key=lambda i: i.created, reverse=True)
        for idea in ideas[:SHOWN]:
            row = self._row(idea)
            self.body.insertWidget(self.body.indexOf(self.empty), row)
            self._rows.append(row)
        self.count.setText(str(len(ideas)))
        self.count.setVisible(bool(ideas))
        self.empty.setVisible(not ideas)
        hidden = len(ideas) - SHOWN
        self.more.setText(_("{n} more in Ideas").format(n=hidden) if hidden > 0 else "")
        self.more.setVisible(hidden > 0)

    def _row(self, idea) -> QWidget:
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(4)
        text = QLabel(idea.text.splitlines()[0] if idea.text else "")
        text.setWordWrap(True)
        text.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        text.setToolTip(idea.text)
        to_task = icon_button("checklist", _("Make it a task for today"))
        to_task.clicked.connect(lambda _c=False, i=idea: self._to_task(i))
        done = icon_button("check", _("Done: clear it from the inbox"))
        done.clicked.connect(lambda _c=False, i=idea: self._done(i))
        line.addWidget(text, 1)
        line.addWidget(to_task)
        line.addWidget(done)
        return row

    def _to_task(self, idea):
        day = self._day() if callable(self._day) else self._day
        self.services.ideas.to_task(idea.id, day if isinstance(day, date) else None)
        self._show_undo(None, _("Now a task for today."))

    def _done(self, idea):
        self.services.ideas.set_done(idea.id, True)
        self._show_undo(idea, _("Cleared."))

    def _show_undo(self, idea, text):
        self._undo_record = idea
        self.undo_text.setText(text)
        self.undo_btn.setVisible(idea is not None)
        self.undo_row.show()

    def _undo(self):
        if self._undo_record is not None:
            self.services.ideas.set_done(self._undo_record.id, False)
        self._undo_record = None
        self.undo_row.hide()
