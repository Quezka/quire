"""Day planner: timeline of classes and events, tasks due, and a day journal."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCalendarWidget, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPlainTextEdit, QScrollArea, QToolButton, QVBoxLayout, QWidgetAction,
)

from ...application.bus import Topic
from ...application.dto import AgendaItem, DayAgenda, ItemKind
from ...application.services import Services
from ...domain import Task, TaskKind
from .. import icons, theme
from ..bridge import ChangeRelay
from ..dialogs import (
    EventDialog, ShiftDialog, TaskDialog, add_menu, class_menu, new_item_menu, to_qdate,
    weekly_shift_menu,
)
from ..formatting import KIND_LABELS, long_date, plural, relative_date
from ..widgets import NO_COLOR, TimeGrid, color_icon
from .common import Card, Page, agenda_block, badge, button, icon_button, menu_button


class TodayView(Page):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.day = self.planner.today()

        # ---- header ----
        prev_btn = icon_button("chevron-left", "Previous day")
        prev_btn.clicked.connect(lambda: self.set_day(self.day - timedelta(days=1)))
        next_btn = icon_button("chevron-right", "Next day")
        next_btn.clicked.connect(lambda: self.set_day(self.day + timedelta(days=1)))
        self.leading.addWidget(prev_btn)
        self.leading.addWidget(next_btn)

        self.calendar = QCalendarWidget()
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.clicked.connect(self._calendar_picked)
        pick = icon_button("calendar-day", "Pick a date")
        pick.setPopupMode(QToolButton.InstantPopup)
        self._calendar_menu = QMenu(pick)
        holder = QWidgetAction(self._calendar_menu)
        holder.setDefaultWidget(self.calendar)
        self._calendar_menu.addAction(holder)
        pick.setMenu(self._calendar_menu)

        self.today_btn = button("Today")
        self.today_btn.clicked.connect(lambda: self.set_day(self.planner.today()))
        add = menu_button("Add", add_menu(self, self.services, lambda: self.day), primary=True)
        self.add_actions(pick, self.today_btn, add)

        # ---- timeline ----
        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(self.grid)
        timeline = Card(padding=6)
        timeline.add(self.scroll, 1)

        # ---- due ----
        due = Card("Due")
        self.due_count = badge()
        due.title_row.insertWidget(1, self.due_count)
        self.tasks = QListWidget()
        self.tasks.itemChanged.connect(self._task_toggled)
        self.tasks.itemDoubleClicked.connect(self._task_open)
        self.quick = QLineEdit(placeholderText="Add a task for this day", clearButtonEnabled=True)
        self.quick.setObjectName("search")
        self._quick_action = self.quick.addAction(icons.icon("plus", theme.current().faint, size=16),
                                                  QLineEdit.LeadingPosition)
        theme.themed(lambda t: self._quick_action.setIcon(icons.icon("plus", t.faint, size=16)))
        self.quick.returnPressed.connect(self._quick_add)
        due.add(self.tasks, 1)
        due.add(self.quick)

        # ---- journal ----
        notes = Card("Day notes")
        self.journal = QPlainTextEdit(placeholderText="Anything to remember about this day…")
        self.journal.setObjectName("bare")
        notes.add(self.journal, 1)
        self._journal_timer = QTimer(self, singleShot=True, interval=600,
                                     timeout=self.flush_journal)
        self.journal.textChanged.connect(self._journal_edited)
        self._journal_day: date | None = None
        self._journal_dirty = False

        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(due, 3)
        side.addWidget(notes, 2)
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(timeline, 5)
        body.addLayout(side, 3)
        self.root.addLayout(body, 1)

        relay.changed.connect(self._changed)
        theme.manager().changed.connect(lambda _t: self.refresh())
        # Roll over to the new day at midnight if the app is left open.
        self._last_seen_today = self.day
        QTimer(self, interval=60_000, timeout=self._check_midnight).start()
        self.set_day(self.day)

    # ---- navigation -----------------------------------------------------

    def set_day(self, day: date):
        self.flush_journal()
        self.day = day
        self.calendar.setSelectedDate(to_qdate(day))
        agenda = self.refresh()
        self.journal.blockSignals(True)
        self.journal.setPlainText(agenda.journal)
        self.journal.blockSignals(False)
        self._journal_day = day
        QTimer.singleShot(0, self._scroll_to_focus)

    def _calendar_picked(self, qdate):
        self._calendar_menu.close()
        self.set_day(qdate.toPython())

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
        else:
            target = self.grid.first_daytime_start(8 * 60 + 30) - 30
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
        if topic in (Topic.COURSES, Topic.EVENTS, Topic.TASKS, Topic.WORK):
            self.refresh()

    def refresh(self) -> DayAgenda:
        agenda = self.planner.day_agenda(self.day)
        today = self.planner.today()
        self.today_btn.setEnabled(not agenda.is_today)
        title = long_date(agenda.day)
        if agenda.day.year != today.year:
            title += f" {agenda.day.year}"
        self.title.setText(title)

        self.grid.set_data(1, [agenda_block(i, 0) for i in agenda.items],
                           now_col=0 if agenda.is_today else -1)
        self._fill_tasks(agenda, today)

        parts = [relative_date(agenda.day, today)]
        if agenda.class_count:
            parts.append(plural(agenda.class_count, "class", "es"))
        if agenda.event_count:
            parts.append(plural(agenda.event_count, "event"))
        if agenda.shift_count:
            parts.append(plural(agenda.shift_count, "work shift"))
        if not agenda.has_courses:
            parts.append("add your timetable in Week")
        self.subtitle.setText(" · ".join(parts))
        self.due_count.setText(str(agenda.open_task_count))
        self.due_count.setVisible(agenda.open_task_count > 0)
        return agenda

    def _fill_tasks(self, agenda: DayAgenda, today: date):
        t = theme.current()
        self.tasks.blockSignals(True)
        self.tasks.clear()
        for entry in agenda.tasks:
            task = entry.task
            meta = [KIND_LABELS[task.kind]] if task.kind is not TaskKind.TASK else []
            if entry.course:
                meta.append(entry.course.name)
            if entry.overdue:
                meta.append("overdue · " + relative_date(task.due, today))
            item = QListWidgetItem(task.title + ("\n" + " · ".join(meta) if meta else ""))
            item.setData(Qt.UserRole, task.id)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if task.done else Qt.Unchecked)
            item.setIcon(color_icon(entry.course.color if entry.course else NO_COLOR, 10))
            if task.done:
                font = item.font()
                font.setStrikeOut(True)
                item.setFont(font)
                item.setForeground(QColor(t.faint))
            elif entry.overdue:
                item.setForeground(QColor(t.danger))
            self.tasks.addItem(item)
        if not agenda.tasks:
            empty = QListWidgetItem("Nothing due. Nice.")
            empty.setFlags(Qt.NoItemFlags)
            empty.setForeground(QColor(t.faint))
            self.tasks.addItem(empty)
        self.tasks.blockSignals(False)

    # ---- interaction ----------------------------------------------------

    def _block_activated(self, item: AgendaItem, pos):
        if item.kind is ItemKind.EVENT:
            EventDialog(self.services, item.ref_id, parent=self).exec()
        elif item.kind is ItemKind.SHIFT:
            ShiftDialog(self.services, item.ref_id, parent=self).exec()
        elif item.kind is ItemKind.WEEKLY_SHIFT:
            weekly_shift_menu(self, self.services, item.ref_id, item.origin, pos)
        else:
            class_menu(self, self.services, item.ref_id, item.day, pos, self.openClassNote.emit)

    def _empty_activated(self, _col, minute):
        new_item_menu(self, self.services, self.day, minute)

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
