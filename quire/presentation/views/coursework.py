"""All tasks, homework and exams, grouped by when they're due."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.services import Services
from ...domain import DueBucket
from ..bridge import ChangeRelay
from ..dialogs import TaskDialog, confirm, fill_course_combo
from ..formatting import BUCKET_LABELS, KIND_LABELS, relative_date
from ..widgets import ALERT_COLOR, color_icon


class CourseworkView(QWidget):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services

        new = QPushButton("New task…")
        new.clicked.connect(self.new_task)
        self.course = QComboBox()
        self.course.setMinimumWidth(180)
        fill_course_combo(self.course, services.timetable.courses(), "All courses")
        self.course.currentIndexChanged.connect(self.refresh)
        self.show_done = QCheckBox("Show completed")
        self.show_done.toggled.connect(self.refresh)

        bar = QHBoxLayout()
        bar.addWidget(new)
        bar.addStretch()
        bar.addWidget(QLabel("Course"))
        bar.addWidget(self.course)
        bar.addWidget(self.show_done)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Task", "Type", "Course", "Due"])
        self.tree.setUniformRowHeights(True)
        head = self.tree.header()
        head.setStretchLastSection(False)
        head.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in (1, 2, 3):
            head.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.tree.itemChanged.connect(self._toggled)
        self.tree.itemDoubleClicked.connect(self._open)
        QShortcut(QKeySequence.Delete, self.tree, activated=self._delete_selected,
                  context=Qt.WidgetShortcut)

        self.empty = QLabel("No tasks here. Press “New task…” or Ctrl+T.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.empty)

        relay.changed.connect(self._changed)
        self.refresh()

    def _changed(self, topic: Topic):
        if topic is Topic.COURSES:
            fill_course_combo(self.course, self.services.timetable.courses(), "All courses")
        if topic in (Topic.COURSES, Topic.TASKS):
            self.refresh()

    def new_task(self):
        TaskDialog(self.services, course_id=self.course.currentData(), parent=self).exec()

    def refresh(self):
        today = self.services.planner.today()
        groups = self.services.tasks.groups(self.show_done.isChecked(),
                                            self.course.currentData())
        muted = self.palette().placeholderText()
        self.tree.blockSignals(True)
        self.tree.clear()
        for group in groups:
            parent = QTreeWidgetItem([f"{BUCKET_LABELS[group.bucket]}  ({len(group.items)})"])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFlags(Qt.ItemIsEnabled)
            if group.bucket is DueBucket.OVERDUE:
                parent.setForeground(0, QColor(ALERT_COLOR))
            self.tree.addTopLevelItem(parent)
            parent.setFirstColumnSpanned(True)
            for entry in group.items:
                t = entry.task
                child = QTreeWidgetItem([
                    t.title,
                    KIND_LABELS[t.kind],
                    entry.course.name if entry.course else "",
                    relative_date(t.due, today) if t.due else "",
                ])
                child.setData(0, Qt.UserRole, t.id)
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked if t.done else Qt.Unchecked)
                if entry.course:
                    child.setIcon(2, color_icon(entry.course.color))
                if t.details:
                    child.setToolTip(0, t.details)
                if t.done:
                    f = child.font(0)
                    f.setStrikeOut(True)
                    child.setFont(0, f)
                    for col in range(4):
                        child.setForeground(col, muted)
                elif entry.overdue:
                    child.setForeground(3, QColor(ALERT_COLOR))
                parent.addChild(child)
            parent.setExpanded(True)
        self.tree.blockSignals(False)
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
        if task_id is not None and confirm(self, "Delete task", f"Delete “{item.text(0)}”?"):
            self.services.tasks.delete(task_id)
