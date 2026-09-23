"""Day planner: timeline of classes and events, tasks due, and a day journal."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDateEdit, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.dto import AgendaItem, DayAgenda, ItemKind
from ...application.services import Services
from ...domain import Task, TaskKind
from ..bridge import ChangeRelay
from ..dialogs import EventDialog, TaskDialog, class_menu, to_qdate
from ..formatting import KIND_LABELS, long_date, plural, relative_date
from ..widgets import ALERT_COLOR, NO_COLOR, TimeGrid, color_icon, scaled_font
from .common import agenda_block, nav_button


class TodayView(QWidget):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.day = self.planner.today()

        prev_btn = nav_button("‹")
        prev_btn.clicked.connect(lambda: self.set_day(self.day - timedelta(days=1)))
        next_btn = nav_button("›")
        next_btn.clicked.connect(lambda: self.set_day(self.day + timedelta(days=1)))
        self.today_btn = QPushButton("Today")
        self.today_btn.clicked.connect(lambda: self.set_day(self.planner.today()))
        self.title = QLabel()
        self.title.setFont(scaled_font(self.title, 1.6, bold=True))
        self.summary = QLabel()
        self.summary.setEnabled(False)
        self.date_edit = QDateEdit(calendarPopup=True)
        self.date_edit.setDisplayFormat("ddd d MMM yyyy")
        self.date_edit.dateChanged.connect(lambda qd: self.set_day(qd.toPython()))

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.title)
        titles.addWidget(self.summary)
        header = QHBoxLayout()
        header.addWidget(prev_btn)
        header.addWidget(next_btn)
        header.addSpacing(6)
        header.addLayout(titles)
        header.addStretch()
        header.addWidget(self.date_edit)
        header.addWidget(self.today_btn)

        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        self.scroll.setWidget(self.grid)

        self.tasks = QListWidget()
        self.tasks.itemChanged.connect(self._task_toggled)
        self.tasks.itemDoubleClicked.connect(self._task_open)
        self.quick = QLineEdit(placeholderText="Add a task for this day, press Enter",
                               clearButtonEnabled=True)
        self.quick.returnPressed.connect(self._quick_add)
        self.journal = QPlainTextEdit(placeholderText="Anything to remember about this day…")
        self._journal_timer = QTimer(self, singleShot=True, interval=600,
                                     timeout=self.flush_journal)
        self.journal.textChanged.connect(self._journal_edited)
        self._journal_day: date | None = None
        self._journal_dirty = False

        side = QWidget()
        side_layout = QVBoxLayout(side)
        side_layout.setContentsMargins(8, 0, 0, 0)
        side_layout.addWidget(QLabel("<b>Due</b>"))
        side_layout.addWidget(self.tasks, 3)
        side_layout.addWidget(self.quick)
        side_layout.addSpacing(8)
        side_layout.addWidget(QLabel("<b>Day notes</b>"))
        side_layout.addWidget(self.journal, 2)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.scroll)
        splitter.addWidget(side)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(splitter, 1)

        relay.changed.connect(self._changed)
        # Roll over to the new day at midnight if the app is left open.
        self._last_seen_today = self.day
        QTimer(self, interval=60_000, timeout=self._check_midnight).start()
        self.set_day(self.day)

    # ---- navigation -----------------------------------------------------

    def set_day(self, day: date):
        self.flush_journal()
        self.day = day
        self.date_edit.blockSignals(True)
        self.date_edit.setDate(to_qdate(day))
        self.date_edit.blockSignals(False)
        agenda = self.refresh()
        self.journal.blockSignals(True)
        self.journal.setPlainText(agenda.journal)
        self.journal.blockSignals(False)
        self._journal_day = day
        QTimer.singleShot(0, self._scroll_to_focus)

    def _check_midnight(self):
        today = self.planner.today()
        if today != self._last_seen_today:
            if self.day == self._last_seen_today:
                self.set_day(today)
            self._last_seen_today = today

    def _scroll_to_focus(self):
        if self.day == self.planner.today():
            now = datetime.now()
            target = now.hour * 60 + now.minute - 60
        elif self.grid.blocks:
            target = min(b.start for b in self.grid.blocks) - 30
        else:
            target = 8 * 60
        self.scroll.verticalScrollBar().setValue(int(self.grid.y_for(target)) - TimeGrid.PAD)

    # ---- journal --------------------------------------------------------

    def _journal_edited(self):
        self._journal_dirty = True
        self._journal_timer.start()

    def flush_journal(self):
        self._journal_timer.stop()
        if self._journal_dirty and self._journal_day is not None:
            self.planner.save_journal(self._journal_day, self.journal.toPlainText())
        self._journal_dirty = False

    # ---- rendering ------------------------------------------------------

    def _changed(self, topic: Topic):
        if topic in (Topic.COURSES, Topic.EVENTS, Topic.TASKS):
            self.refresh()

    def refresh(self) -> DayAgenda:
        agenda = self.planner.day_agenda(self.day)
        today = self.planner.today()
        self.today_btn.setEnabled(not agenda.is_today)
        title = long_date(agenda.day)
        if agenda.is_today:
            title = f"Today · {title}"
        elif agenda.day.year != today.year:
            title += f" {agenda.day.year}"
        self.title.setText(title)

        self.grid.set_data(1, [agenda_block(i, 0) for i in agenda.items],
                           now_col=0 if agenda.is_today else -1)
        self._fill_tasks(agenda, today)

        parts = []
        if agenda.class_count:
            parts.append(plural(agenda.class_count, "class", "es"))
        if agenda.event_count:
            parts.append(plural(agenda.event_count, "event"))
        parts.append(plural(agenda.open_task_count, "task") + " left")
        if not agenda.has_courses:
            parts.append("add your timetable in the Week tab")
        self.summary.setText(" · ".join(parts))
        return agenda

    def _fill_tasks(self, agenda: DayAgenda, today: date):
        muted = self.palette().placeholderText()
        self.tasks.blockSignals(True)
        self.tasks.clear()
        for entry in agenda.tasks:
            t = entry.task
            meta = [KIND_LABELS[t.kind]] if t.kind is not TaskKind.TASK else []
            if entry.course:
                meta.append(entry.course.name)
            if entry.overdue:
                meta.append("overdue · " + relative_date(t.due, today))
            item = QListWidgetItem(t.title + ("\n" + " · ".join(meta) if meta else ""))
            item.setData(Qt.UserRole, t.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if t.done else Qt.Unchecked)
            item.setIcon(color_icon(entry.course.color if entry.course else NO_COLOR))
            if t.done:
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(muted)
            elif entry.overdue:
                item.setForeground(QColor(ALERT_COLOR))
            self.tasks.addItem(item)
        if not agenda.tasks:
            empty = QListWidgetItem("Nothing due. Nice.")
            empty.setFlags(Qt.NoItemFlags)
            self.tasks.addItem(empty)
        self.tasks.blockSignals(False)

    # ---- interaction ----------------------------------------------------

    def _block_activated(self, item: AgendaItem, pos):
        if item.kind is ItemKind.EVENT:
            EventDialog(self.services, item.ref_id, parent=self).exec()
        else:
            class_menu(self, self.services, item.ref_id, item.day, pos, self.openClassNote.emit)

    def _empty_activated(self, _col, minute):
        EventDialog(self.services, day=self.day, start=minute, parent=self).exec()

    def _task_toggled(self, item: QListWidgetItem):
        task_id = item.data(Qt.UserRole)
        if task_id is not None:
            # Deferred: the refresh this triggers rebuilds the list we're inside.
            done = item.checkState() == Qt.Checked
            QTimer.singleShot(0, lambda: self.services.tasks.set_done(task_id, done))

    def _task_open(self, item: QListWidgetItem):
        task_id = item.data(Qt.UserRole)
        if task_id is not None:
            TaskDialog(self.services, task_id, parent=self).exec()

    def _quick_add(self):
        title = self.quick.text().strip()
        if title:
            self.services.tasks.save(Task(title, due=self.day))
            self.quick.clear()
