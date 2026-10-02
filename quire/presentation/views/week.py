"""Weekly school timetable with one-off events layered on top."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QMenu, QScrollArea

from ...application.bus import Topic
from ...application.dto import AgendaItem, ItemKind
from ...application.services import Services
from ..bridge import ChangeRelay
from ..dialogs import (
    CoursesDialog, EventDialog, JobsDialog, ShiftDialog, add_menu, class_menu, new_item_menu,
    weekly_shift_menu,
)
from ..widgets import GridHeader, TimeGrid, TimelineZoom
from .common import Card, Page, agenda_block, button, icon_button, menu_button, zoom_controls
from ..i18n import _, month_name, month_short, weekday_short


class WeekView(Page):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.anchor = self.planner.today()
        self.days: tuple[date, ...] = ()

        prev_btn = icon_button("chevron-left", _("Previous week"))
        prev_btn.clicked.connect(lambda: self.set_week(self.anchor - timedelta(days=7)))
        next_btn = icon_button("chevron-right", _("Next week"))
        next_btn.clicked.connect(lambda: self.set_week(self.anchor + timedelta(days=7)))
        self.leading.addWidget(prev_btn)
        self.leading.addWidget(next_btn)

        timetable = QMenu(self)
        timetable.addAction(_("Courses && class times…"),
                            lambda: CoursesDialog(self.services, self).exec())
        timetable.addAction(_("Jobs && work schedule…"),
                            lambda: JobsDialog(self.services, self).exec())
        self.this_week = button(_("This week"))
        self.this_week.clicked.connect(lambda: self.set_week(self.planner.today()))
        add = menu_button(_("Add"), add_menu(self, self.services, self._default_day), primary=True)
        self.add_actions(menu_button(_("Timetable"), timetable, "week"), self.this_week, add)

        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.grid.swiped.connect(lambda step: self.set_week(self.anchor + timedelta(days=7 * step)))
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.grid)
        self.zoom = TimelineZoom(self.grid, self.scroll, "week", self)
        self.header.insertWidget(self.header.count() - 3, zoom_controls(self, self.zoom))
        self.day_header = GridHeader(self.grid)
        self.day_header.setContentsMargins(
            0, 0, self.scroll.verticalScrollBar().sizeHint().width(), 0)

        card = Card(padding=6)
        card.body.setSpacing(0)
        card.add(self.day_header)
        card.add(self.scroll, 1)
        self.root.addWidget(card, 1)

        relay.changed.connect(self._changed)
        self.set_week(self.anchor)

    def _default_day(self) -> date:
        today = self.planner.today()
        return today if today in self.days else self.days[0] if self.days else today

    def set_week(self, any_day: date):
        self.anchor = any_day
        self.refresh()
        QTimer.singleShot(0, self._scroll_to_focus)

    def _scroll_to_focus(self):
        target = self.grid.first_daytime_start() - 30
        if not self.zoom.fit:  # when fitted, the whole day is already in view
            self.scroll.verticalScrollBar().setValue(int(self.grid.y_for(target)) - TimeGrid.PAD)

    def _changed(self, topic: Topic):
        if topic in (Topic.COURSES, Topic.EVENTS, Topic.WORK):
            self.refresh()

    def refresh(self):
        week = self.planner.week_agenda(self.anchor)
        self.days = week.days
        monday, sunday = week.monday, week.monday + timedelta(days=6)
        self.this_week.setEnabled(week.today_index is None)
        if monday.month == sunday.month:
            self.title.setText(f"{month_name(monday)} {monday.year}")
        else:
            self.title.setText(f"{month_short(monday).capitalize()} – "
                               f"{month_short(sunday)} {sunday.year}")

        now_col = -1 if week.today_index is None else week.today_index
        blocks = [agenda_block(i, week.days.index(i.day)) for i in week.items]
        self.grid.set_data(len(week.days), blocks, now_col)
        self.zoom.apply()
        self.day_header.set_days([(weekday_short(d), d.day) for d in week.days], now_col)

        if week.has_courses:
            self.subtitle.setText(_("Double-click a class for notes and homework, or an empty slot to add an event or work shift"))
        else:
            self.subtitle.setText(_("Add your classes and work schedule under Timetable"))

    def _block_activated(self, item: AgendaItem, pos):
        if item.kind is ItemKind.EVENT:
            EventDialog(self.services, item.ref_id, parent=self).exec()
        elif item.kind is ItemKind.SHIFT:
            ShiftDialog(self.services, item.ref_id, parent=self).exec()
        elif item.kind is ItemKind.WEEKLY_SHIFT:
            weekly_shift_menu(self, self.services, item.ref_id, item.origin, pos)
        else:
            class_menu(self, self.services, item.ref_id, item.day, pos, self.openClassNote.emit)

    def _empty_activated(self, col, minute):
        new_item_menu(self, self.services, self.days[col], minute)
