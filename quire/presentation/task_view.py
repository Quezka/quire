"""Read-only view of one task, for checking it; editing is one click away."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QTextBrowser, QVBoxLayout,
)

from ..application.services import Services
from ..domain import NotFound, TaskKind
from . import theme
from .dialogs import TaskDialog
from .formatting import KIND_LABELS, long_date, relative_date
from .i18n import _


def chip(text: str, color: str | None = None, role: str = "chip") -> QLabel:
    """A small rounded label; `color` tints it (e.g. with the subject's colour)."""
    label = QLabel(text, objectName=role)
    if color:
        c = QColor(color)
        label.setStyleSheet(f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 0.18);")
    return label


class TaskView(QDialog):
    def __init__(self, services: Services, task_id: int, parent=None):
        super().__init__(parent)
        self.services = services
        self.task_id = task_id
        self.setWindowTitle(_("Task"))
        self.setMinimumWidth(500)

        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        self.title = QLabel(objectName="sheetTitle")
        self.title.setWordWrap(True)
        self.title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.source = QLabel(objectName="hint")
        self.body = QTextBrowser(objectName="sheetBody", openExternalLinks=True)
        self.body.setMinimumHeight(140)
        self.empty = QLabel(_("No details."), objectName="hint")

        self.edit_btn = QPushButton(_("Edit…"))
        self.edit_btn.setToolTip(_("Edit this task (E)"))
        self.edit_btn.clicked.connect(self._edit)
        close = QPushButton(_("Close"))
        close.clicked.connect(self.accept)
        self.done_btn = QPushButton(objectName="primary")
        self.done_btn.setToolTip(_("Space"))
        self.done_btn.clicked.connect(self._toggle_done)
        buttons = QHBoxLayout()
        buttons.addWidget(self.edit_btn)
        buttons.addStretch()
        buttons.addWidget(close)
        buttons.addWidget(self.done_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)
        layout.addLayout(self.chips)
        layout.addWidget(self.title)
        layout.addWidget(self.source)
        layout.addWidget(self.body, 1)
        layout.addWidget(self.empty)
        layout.addSpacing(4)
        layout.addLayout(buttons)

        QShortcut(QKeySequence("E"), self, activated=self._edit)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._toggle_done)
        self.done_btn.setFocus()
        self.refresh()

    def refresh(self):
        try:
            task = self.services.tasks.task(self.task_id)
        except NotFound:  # deleted from the editor
            self.accept()
            return
        t = theme.current()
        today = self.services.planner.today()
        course = next((c for c in self.services.timetable.courses() if c.id == task.course_id),
                      None)

        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if course:
            self.chips.addWidget(chip(course.name, course.color))
        kind = _("Test") if task.kind is TaskKind.EXAM else KIND_LABELS[task.kind]
        self.chips.addWidget(chip(kind))
        if task.due:
            when = relative_date(task.due, today)
            if when in (_("Today"), _("Tomorrow"), _("Yesterday")):
                when = when.lower()  # "Due tomorrow", but "Due Friday"
            due = chip(_("Due {when}").format(when=when),
                       role="chipDanger" if task.is_overdue(today) else "chip")
            due.setToolTip(long_date(task.due))
            self.chips.addWidget(due)
        if task.done:
            self.chips.addWidget(chip(_("Done"), t.success))
        self.chips.addStretch()

        self.title.setText(task.title)
        font = self.title.font()
        font.setStrikeOut(task.done)
        self.title.setFont(font)

        register = self.services.school.status().register
        self.source.setText(_("From {register}").format(register=register)
                            if task.external_id else "")
        self.source.setVisible(bool(task.external_id))
        self.body.setPlainText(task.details)
        self.body.setVisible(bool(task.details.strip()))
        self.empty.setVisible(not task.details.strip())

        self.done_btn.setText(_("Mark as not done") if task.done else _("Mark as done"))
        # Not `self.done`: that would hide QDialog.done() and break closing the dialog.
        self._is_done = task.done

    def _toggle_done(self):
        self.services.tasks.set_done(self.task_id, not self._is_done)
        self.refresh()

    def _edit(self):
        TaskDialog(self.services, self.task_id, parent=self).exec()
        self.refresh()
