"""All tasks, homework and exams, grouped by when they're due."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import QComboBox, QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem

from ...application.bus import Topic
from ...application.services import Services
from ...domain import DueBucket
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import TaskDialog, confirm, fill_course_combo
from ..formatting import BUCKET_LABELS, KIND_LABELS, plural, relative_date
from ..widgets import color_icon
from .common import Card, Page, button, primary_button
from ..i18n import _


class CourseworkView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.title.setText(_("Coursework"))

        self.course = QComboBox()
        self.course.setMinimumWidth(190)
        fill_course_combo(self.course, services.timetable.courses(), _("All courses"))
        self.course.currentIndexChanged.connect(self.refresh)
        self.show_done = button(_("Show completed"), "check")
        self.show_done.setCheckable(True)
        self.show_done.toggled.connect(self.refresh)
        new = primary_button(_("Task"))
        new.clicked.connect(self.new_task)
        self.add_actions(self.course, self.show_done, new)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([_("TASK"), _("TYPE"), _("COURSE"), _("DUE")])
        self.tree.setUniformRowHeights(True)
        self.tree.setIndentation(14)
        head = self.tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            head.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._toggled)
        self.tree.itemDoubleClicked.connect(self._open)
        QShortcut(QKeySequence.Delete, self.tree, activated=self._delete_selected,
                  context=Qt.WidgetShortcut)

        self.empty = QLabel(_("Nothing to do. Add a task with the button above or Ctrl+T."),
                            objectName="hint")
        self.empty.setAlignment(Qt.AlignCenter)

        card = Card(padding=10)
        card.add(self.tree, 1)
        card.add(self.empty, 1)
        self.root.addWidget(card, 1)

        relay.changed.connect(self._changed)
        theme.manager().changed.connect(self._theme_changed)
        self.refresh()

    def _changed(self, topic: Topic):
        if topic is Topic.COURSES:
            fill_course_combo(self.course, self.services.timetable.courses(), _("All courses"))
        if topic in (Topic.COURSES, Topic.TASKS):
            self.refresh()

    def new_task(self):
        TaskDialog(self.services, course_id=self.course.currentData(), parent=self).exec()

    def _theme_changed(self, _theme):
        self.refresh()

    def refresh(self):
        t = theme.current()
        today = self.services.planner.today()
        groups = self.services.tasks.groups(self.show_done.isChecked(),
                                            self.course.currentData())
        open_count = sum(len(g.items) for g in groups if g.bucket is not DueBucket.DONE)
        overdue = sum(len(g.items) for g in groups if g.bucket is DueBucket.OVERDUE)
        summary = [plural(open_count, "open task")]
        if overdue:
            summary.append(_("{count} overdue").format(count=overdue))
        self.subtitle.setText(" · ".join(summary))

        self.tree.blockSignals(True)
        self.tree.clear()
        for group in groups:
            parent = QTreeWidgetItem([f"{BUCKET_LABELS[group.bucket]}   {len(group.items)}"])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFlags(Qt.ItemIsEnabled)
            parent.setForeground(0, QColor(t.danger if group.bucket is DueBucket.OVERDUE
                                           else t.muted))
            self.tree.addTopLevelItem(parent)
            parent.setFirstColumnSpanned(True)
            for entry in group.items:
                task = entry.task
                child = QTreeWidgetItem([
                    task.title,
                    KIND_LABELS[task.kind],
                    entry.course.name if entry.course else "",
                    relative_date(task.due, today) if task.due else "",
                ])
                child.setData(0, Qt.UserRole, task.id)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked if task.done else Qt.Unchecked)
                for col in (1, 3):
                    child.setForeground(col, QColor(t.muted))
                if entry.course:
                    child.setIcon(2, color_icon(entry.course.color, 10))
                if task.details:
                    child.setToolTip(0, task.details)
                if task.done:
                    f = child.font(0)
                    f.setStrikeOut(True)
                    child.setFont(0, f)
                    for col in range(4):
                        child.setForeground(col, QColor(t.faint))
                elif entry.overdue:
                    child.setForeground(3, QColor(t.danger))
                parent.addChild(child)
            parent.setExpanded(True)
        self.tree.blockSignals(False)
        self.tree.setVisible(bool(groups))
        self.empty.setVisible(not groups)

    def _toggled(self, item: QTreeWidgetItem, column: int):
        task_id = item.data(0, Qt.UserRole)
        if task_id is not None and column == 0:
            done = item.checkState(0) == Qt.Checked
            QTimer.singleShot(0, lambda: self.services.tasks.set_done(task_id, done))

    def _open(self, item: QTreeWidgetItem, _column: int):
        task_id = item.data(0, Qt.UserRole)
        if task_id is not None:
            TaskDialog(self.services, task_id, parent=self).exec()

    def _delete_selected(self):
        item = self.tree.currentItem()
        task_id = item.data(0, Qt.UserRole) if item else None
        if task_id is not None and confirm(self, _("Delete task"), _("Delete “{title}”?").format(title=item.text(0))):
            self.services.tasks.delete(task_id)
