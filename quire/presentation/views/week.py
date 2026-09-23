"""Weekly school timetable with one-off events layered on top."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QScrollArea

from ...application.bus import Topic
from ...application.dto import AgendaItem, ItemKind
from ...application.services import Services
from ..bridge import ChangeRelay
from ..dialogs import CoursesDialog, EventDialog, class_menu
from ..widgets import GridHeader, TimeGrid
from .common import Card, Page, agenda_block, button, icon_button, primary_button


class WeekView(Page):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.anchor = self.planner.today()
        self.days: tuple[date, ...] = ()

        prev_btn = icon_button("chevron-left", "Previous week")
        prev_btn.clicked.connect(lambda: self.set_week(self.anchor - timedelta(days=7)))
        next_btn = icon_button("chevron-right", "Next week")
        next_btn.clicked.connect(lambda: self.set_week(self.anchor + timedelta(days=7)))
        self.leading.addWidget(prev_btn)
        self.leading.addWidget(next_btn)

        courses = button("Courses", "school")
        courses.clicked.connect(lambda: CoursesDialog(self.services, self).exec())
        self.this_week = button("This week")
        self.this_week.clicked.connect(lambda: self.set_week(self.planner.today()))
        add_event = primary_button("Event")
        add_event.clicked.connect(lambda: EventDialog(
            self.services, day=self.anchor, parent=self).exec())
        self.add_actions(courses, self.this_week, add_event)

        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.scroll = QScrollArea(widgetResizable=True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.grid)
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

    def set_week(self, any_day: date):
        self.anchor = any_day
        self.refresh()
        QTimer.singleShot(0, self._scroll_to_focus)

    def _scroll_to_focus(self):
        target = min((b.start for b in self.grid.blocks), default=8 * 60 + 30) - 30
        self.scroll.verticalScrollBar().setValue(int(self.grid.y_for(target)) - TimeGrid.PAD)

    def _changed(self, topic: Topic):
        if topic in (Topic.COURSES, Topic.EVENTS):
            self.refresh()

    def refresh(self):
        week = self.planner.week_agenda(self.anchor)
        self.days = week.days
        monday, sunday = week.monday, week.monday + timedelta(days=6)
        self.this_week.setEnabled(week.today_index is None)
        if monday.month == sunday.month:
            self.title.setText(f"{monday:%B %Y}")
        else:
            self.title.setText(f"{monday:%b} – {sunday:%b %Y}")

        now_col = -1 if week.today_index is None else week.today_index
        blocks = [agenda_block(i, week.days.index(i.day)) for i in week.items]
        self.grid.set_data(len(week.days), blocks, now_col)
        self.day_header.set_days([(f"{d:%a}", d.day) for d in week.days], now_col)

        if week.has_courses:
            self.subtitle.setText("Double-click a class for notes and homework, "
                                  "or an empty slot to add an event")
        else:
            self.subtitle.setText("No classes yet. Add your subjects under Courses")

    def _block_activated(self, item: AgendaItem, pos):
        if item.kind is ItemKind.EVENT:
            EventDialog(self.services, item.ref_id, parent=self).exec()
        else:
            class_menu(self, self.services, item.ref_id, item.day, pos, self.openClassNote.emit)

    def _empty_activated(self, col, minute):
        EventDialog(self.services, day=self.days[col], start=minute, parent=self).exec()
