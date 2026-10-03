"""Day planner: timeline of classes and events, tasks due, and a day journal."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCalendarWidget, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QPlainTextEdit, QScrollArea, QToolButton, QVBoxLayout, QWidgetAction,
)

from ...application.bus import Topic
from ...application.dto import AgendaItem, DayAgenda, ItemKind
from ...application.services import Services
from ...application.inputs import TaskInput
from ...application.types import TaskKind
from .. import icons, theme
from ..bridge import ChangeRelay
from ..dialogs import (
    EventDialog, ShiftDialog, add_menu, class_menu, new_item_menu, to_qdate,
    weekly_shift_menu,
)
from ..formatting import KIND_LABELS, long_date, plural, relative_date, was_due
from ..task_view import TaskView
from ..widgets import TimeGrid, TimelineZoom, TwoLineDelegate
from .common import (
    Card, Page, agenda_block, badge, button, icon_button, menu_button, zoom_controls,
)
from ..i18n import _


class TodayView(Page):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.day = self.planner.today()
        self._slide = None  # (animation, [old picture, new picture]) once first used
        self._step = 1

        # ---- header ----
        prev_btn = icon_button("chevron-left", _("Previous day"))
        prev_btn.clicked.connect(lambda: self.go_to(self.day - timedelta(days=1)))
        next_btn = icon_button("chevron-right", _("Next day"))
        next_btn.clicked.connect(lambda: self.go_to(self.day + timedelta(days=1)))
        self.leading.addWidget(prev_btn)
        self.leading.addWidget(next_btn)

        self.calendar = QCalendarWidget()
        self.calendar.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.calendar.clicked.connect(self._calendar_picked)
        pick = icon_button("calendar-day", _("Pick a date"))
        pick.setPopupMode(QToolButton.InstantPopup)
        self._calendar_menu = QMenu(pick)
        holder = QWidgetAction(self._calendar_menu)
        holder.setDefaultWidget(self.calendar)
        self._calendar_menu.addAction(holder)
        pick.setMenu(self._calendar_menu)

        self.today_btn = button(_("Today"))
        self.today_btn.clicked.connect(lambda: self.go_to(self.planner.today()))
        add = menu_button(_("Add"), add_menu(self, self.services, lambda: self.day), primary=True)
        self.add_actions(pick, self.today_btn, add)

        # ---- timeline ----
        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.grid.swiped.connect(lambda step: self.go_to(self.day + timedelta(days=step)))
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(self.grid)
        self.zoom = TimelineZoom(self.grid, self.scroll, "today", self)
        self.header.insertWidget(self.header.count() - 3, zoom_controls(self, self.zoom))
        timeline = Card(padding=6)
        timeline.add(self.scroll, 1)

        # ---- due ----
        due = Card(_("Due"))
        self.due_count = badge()
        due.title_row.insertWidget(1, self.due_count)
        self.tasks = QListWidget()
        self.tasks.setItemDelegate(TwoLineDelegate(self.tasks))
        self.tasks.setMouseTracking(True)
        self.tasks.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tasks.itemChanged.connect(self._task_toggled)
        self.tasks.itemDoubleClicked.connect(self._task_open)
        self.quick = QLineEdit(placeholderText=_("Add a task for this day"), clearButtonEnabled=True)
        self.quick.setObjectName("search")
        self._quick_action = self.quick.addAction(icons.icon("plus", theme.current().faint, size=16),
                                                  QLineEdit.LeadingPosition)
        theme.themed(lambda t: self._quick_action.setIcon(icons.icon("plus", t.faint, size=16)))
        self.quick.returnPressed.connect(self._quick_add)
        due.add(self.tasks, 1)
        due.add(self.quick)

        # ---- journal ----
        notes = Card(_("Day notes"))
        self.journal = QPlainTextEdit(placeholderText=_("Anything to remember about this day…"))
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
        side.addWidget(notes, 1)
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(timeline, 5)
        body.addLayout(side, 3)
        self.root.addLayout(body, 1)

        relay.changed.connect(self._changed)
        theme.manager().changed.connect(self._theme_changed)
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

    SLIDE_MS = 240

    def _slide_parts(self):
        """The two pictures and the animation behind a day change, made on first use."""
        if self._slide is None:
            view = self.scroll.viewport()
            labels = []
            for _i in range(2):
                label = QLabel(view)
                label.setAttribute(Qt.WA_TransparentForMouseEvents)  # wheel/clicks reach the grid
                label.hide()
                labels.append(label)
            animation = QVariantAnimation(self, duration=self.SLIDE_MS, startValue=0.0,
                                          endValue=1.0)
            animation.setEasingCurve(QEasingCurve.OutCubic)
            animation.valueChanged.connect(self._slide_to)
            animation.finished.connect(self._finish_slide)
            self._slide = (animation, labels)
        return self._slide

    def go_to(self, day: date):
        """Change day with a slide: the old day moves out as the new one moves in."""
        if day == self.day:
            return
        view = self.scroll.viewport()
        if not view.isVisible():
            self.set_day(day)
            return
        animation, labels = self._slide_parts()
        self._finish_slide()
        self._step = 1 if day > self.day else -1
        old = view.grab()
        self.set_day(day)
        self._scroll_to_focus()  # settle the new day now so the picture shows where it lands
        new = view.grab()
        for label, picture in zip(labels, (old, new)):
            label.setPixmap(picture)
            label.setGeometry(0, 0, view.width(), view.height())
            label.show()
            label.raise_()
        self._slide_to(0.0)
        animation.start()

    def _slide_to(self, t):
        _animation, labels = self._slide
        width = self.scroll.viewport().width()
        labels[0].move(round(-self._step * width * t), 0)
        labels[1].move(round(self._step * width * (1 - t)), 0)

    def _finish_slide(self):
        if self._slide is None:
            return
        animation, labels = self._slide
        animation.stop()
        for label in labels:
            label.hide()

    def _calendar_picked(self, qdate):
        self._calendar_menu.close()
        self.go_to(qdate.toPython())

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
        if not self.zoom.fit:  # when fitted, the whole day is already in view
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
        elif topic is Topic.JOURNAL:
            self._reload_journal()

    def _reload_journal(self):
        """Show the day note as stored (e.g. after a sync), unless it's being edited."""
        if self._journal_dirty or self._journal_day is None:
            return
        stored = self.planner.journal(self._journal_day)
        if stored != self.journal.toPlainText():
            position = self.journal.textCursor().position()
            self.journal.blockSignals(True)
            self.journal.setPlainText(stored)
            self.journal.blockSignals(False)
            cursor = self.journal.textCursor()
            cursor.setPosition(min(position, len(stored)))
            self.journal.setTextCursor(cursor)

    def _theme_changed(self, _theme):
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
        self.zoom.apply()
        self._fill_tasks(agenda, today)

        parts = [relative_date(agenda.day, today)]
        if agenda.class_count:
            parts.append(plural(agenda.class_count, "class", "es"))
        if agenda.event_count:
            parts.append(plural(agenda.event_count, "event"))
        if agenda.shift_count:
            parts.append(plural(agenda.shift_count, "work shift"))
        if not agenda.has_courses:
            parts.append(_("add your timetable in Week"))
        self.subtitle.setText(" · ".join(parts))
        self.due_count.setText(str(agenda.open_task_count))
        self.due_count.setVisible(agenda.open_task_count > 0)
        return agenda

    def _fill_tasks(self, agenda: DayAgenda, today: date):
        """Viewing today: everything to do, grouped Overdue / Today / Tomorrow / …;
        another day: just what's due that day."""
        t = theme.current()
        self.tasks.blockSignals(True)
        self.tasks.clear()
        last_heading = None
        for entry in agenda.tasks:
            task = entry.task
            if agenda.is_today:
                heading = _("Overdue") if entry.overdue else relative_date(task.due, today)
                if heading != last_heading:
                    last_heading = heading
                    header = QListWidgetItem(heading)
                    header.setData(TwoLineDelegate.HEADER, 2)
                    header.setFlags(Qt.ItemIsEnabled)
                    self.tasks.addItem(header)
            meta = [KIND_LABELS[task.kind]] if task.kind is not TaskKind.TASK else []
            if entry.course:
                meta.insert(0, entry.course.name)
            if entry.overdue:
                meta.insert(0, was_due(task.due, today))
            item = QListWidgetItem(task.title)
            item.setData(Qt.UserRole, task.id)
            item.setData(TwoLineDelegate.META, " · ".join(meta))
            item.setData(TwoLineDelegate.COLOR, entry.course.color if entry.course else None)
            item.setData(TwoLineDelegate.ALERT, entry.overdue)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if task.done else Qt.Unchecked)
            item.setToolTip(_("Double-click to open"))
            self.tasks.addItem(item)
        if not agenda.tasks:
            empty = QListWidgetItem(_("Nothing due. Nice."))
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
            TaskView(self.services, task_id, parent=self).exec()

    def _quick_add(self):
        title = self.quick.text().strip()
        if title:
            self.services.tasks.save(None, TaskInput(title, due=self.day))
            self.quick.clear()
