"""Day planner: timeline of classes and events, tasks due, and the inbox (ideas to decide on)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCalendarWidget, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QScrollArea, QToolButton, QVBoxLayout, QWidget, QWidgetAction,
)

from ...application.bus import Topic
from ...application.dto import AgendaItem, DayAgenda, ItemKind
from ...application.services import Services
from ...application.inputs import TaskInput
from ...application.types import TaskKind
from .. import icons, theme
from ..bridge import ChangeRelay
from ..dialogs import (
    EventDialog, RoutineDialog, ShiftDialog, add_menu, class_menu, new_item_menu, to_qdate,
    weekly_shift_menu,
)
from ..formatting import KIND_LABELS, long_date, plural, relative_date, was_due
from ..task_view import TaskView
from ..widgets import Slider, TimeGrid, TimelineZoom, TwoLineDelegate
from .common import (
    AllDayStrip,
    Card, Page, agenda_block, badge, button, icon_button, menu_button, zoom_controls,
)
from ..i18n import _
from .quick_log import QuickLog
from .now_card import NowCard
from .inbox import InboxCard
from quezka_ui import fit
from quezka_ui.widgets import Segmented


class TodayView(Page):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.day = self.planner.today()

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
        brief = button(_("Digest"))
        brief.setToolTip(_("Digest: your day at a glance"))
        brief.clicked.connect(self._show_digest)
        self.add_actions(pick, brief, self.today_btn, add)

        # ---- timeline ----
        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.grid.swiped.connect(lambda step: self.go_to(self.day + timedelta(days=step)))
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setWidget(self.grid)
        self.zoom = TimelineZoom(self.grid, self.scroll, "today", self)
        self.slider = Slider(self.scroll.viewport())
        self._zoom_box = zoom_controls(self, self.zoom)
        self.header.insertWidget(self.header.count() - 3, self._zoom_box)
        self.all_day = AllDayStrip()
        self.all_day.activated.connect(lambda item: self._block_activated(item, None))
        timeline = Card(padding=6)
        timeline.add(self.all_day)
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

        # ---- inbox (replaced day notes, 0.52) ----
        self.inbox = InboxCard(services, lambda: self.day)
        self.openIdeas = self.inbox.openIdeas

        self.quick_log = QuickLog(services)
        self.now_card = NowCard(services, relay)
        # side column scrolls when short (1366x768 laptop) <- else Due squeezed to 0 rows
        due.setMinimumHeight(180)
        self.inbox.setMinimumHeight(130)
        side_box = QWidget()
        side = QVBoxLayout(side_box)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(16)
        side.addWidget(self.now_card)
        side.addWidget(self.quick_log)
        side.addWidget(due, 2)
        side.addWidget(self.inbox, 1)
        side_scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        side_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        side_scroll.setWidget(side_box)
        side_scroll.viewport().setAutoFillBackground(False)
        side_box.setAutoFillBackground(False)
        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(timeline, 5)
        body.addWidget(side_scroll, 3)
        # compact (split screen): one column at a time, switch on top
        self.view_switch = Segmented([("day", _("Day")), ("todo", _("To do"))])
        self.view_switch.set_value("day")
        self.view_switch.changed.connect(self._show_column)
        self.view_switch.hide()
        self._timeline, self._side = timeline, side_scroll
        self._digest_btn = brief
        self.root.addWidget(self.view_switch, 0, Qt.AlignLeft)
        self.root.addLayout(body, 1)
        fit.on_size_class(self, self._size_class)

        relay.changed.connect(self._changed)
        theme.manager().changed.connect(self._theme_changed)
        # Roll over to the new day at midnight if the app is left open.
        self._last_seen_today = self.day
        QTimer(self, interval=60_000, timeout=self._check_midnight).start()
        self.set_day(self.day)

    # ---- layout ---------------------------------------------------------

    def _size_class(self, size: str):
        compact = size == fit.COMPACT
        self.view_switch.setVisible(compact)
        if compact:
            self._show_column(self.view_switch.value())
        else:
            self._timeline.show()
            self._side.show()
        for w in (self._zoom_box, self._digest_btn):
            if w is not None:
                w.setVisible(not compact)

    def _show_column(self, which):
        self._timeline.setVisible(which == "day")
        self._side.setVisible(which != "day")

    # ---- navigation -----------------------------------------------------

    def _show_digest(self):
        from ..digest import DigestDialog
        DigestDialog(self.services.digest.current(), self).exec()

    def set_day(self, day: date):
        self.day = day
        self.calendar.setSelectedDate(to_qdate(day))
        self.refresh()
        QTimer.singleShot(0, self._scroll_to_focus)

    def go_to(self, day: date):
        """Change day with a slide: the old day moves out as the new one moves in."""
        if day == self.day:
            return

        def change():
            self.set_day(day)
            self._scroll_to_focus()  # settle the new day now so the picture shows where it lands

        self.slider.run(1 if day > self.day else -1, change)

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

    # ---- rendering ------------------------------------------------------

    def _changed(self, topic: Topic):
        if topic in (Topic.COURSES, Topic.EVENTS, Topic.TASKS, Topic.WORK):
            self.refresh()
        if topic in (Topic.IDEAS, Topic.TASKS):
            self.inbox.refresh()
        if topic in (Topic.WATER, Topic.SLEEP, Topic.MEDICINE):
            self.quick_log.refresh()

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

        self.all_day.set_items([i for i in agenda.items if i.is_all_day])
        self.grid.set_data(1, [agenda_block(i, 0) for i in agenda.items if not i.is_all_day],
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
        elif item.kind is ItemKind.ROUTINE:
            RoutineDialog(self.services, item.ref_id, parent=self).exec()
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
