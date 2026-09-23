"""Weekly school timetable with one-off events layered on top."""
from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from ...application.bus import Topic
from ...application.dto import AgendaItem, ItemKind
from ...application.services import Services
from ..bridge import ChangeRelay
from ..dialogs import CoursesDialog, EventDialog, class_menu
from ..widgets import GridHeader, TimeGrid, scaled_font
from .common import agenda_block, nav_button


class WeekView(QWidget):
    openClassNote = Signal(int, object)  # course_id, date

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.planner = services.planner
        self.anchor = self.planner.today()
        self.days: tuple[date, ...] = ()

        prev_btn = nav_button("‹")
        prev_btn.clicked.connect(lambda: self.set_week(self.anchor - timedelta(days=7)))
        next_btn = nav_button("›")
        next_btn.clicked.connect(lambda: self.set_week(self.anchor + timedelta(days=7)))
        self.this_week = QPushButton("This week")
        self.this_week.clicked.connect(lambda: self.set_week(self.planner.today()))
        self.title = QLabel()
        self.title.setFont(scaled_font(self.title, 1.6, bold=True))
        courses = QPushButton("Courses && timetable…")
        courses.clicked.connect(lambda: CoursesDialog(self.services, self).exec())

        header = QHBoxLayout()
        header.addWidget(prev_btn)
        header.addWidget(next_btn)
        header.addSpacing(6)
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(courses)
        header.addWidget(self.this_week)

        self.hint = QLabel()
        self.hint.setEnabled(False)

        self.grid = TimeGrid()
        self.grid.blockActivated.connect(self._block_activated)
        self.grid.emptyActivated.connect(self._empty_activated)
        self.scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.grid)
        self.day_header = GridHeader(self.grid)
        self.day_header.setContentsMargins(
            0, 0, self.scroll.verticalScrollBar().sizeHint().width(), 0)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.hint)
        grid_box = QVBoxLayout()
        grid_box.setSpacing(0)
        grid_box.addWidget(self.day_header)
        grid_box.addWidget(self.scroll, 1)
        layout.addLayout(grid_box, 1)

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
            self.title.setText(f"{monday.day} – {sunday.day} {sunday:%B %Y}")
        else:
            self.title.setText(f"{monday.day} {monday:%b} – {sunday.day} {sunday:%b %Y}")

        now_col = -1 if week.today_index is None else week.today_index
        blocks = [agenda_block(i, week.days.index(i.day)) for i in week.items]
        self.grid.set_data(len(week.days), blocks, now_col)
        self.day_header.set_labels([f"{d:%a} {d.day}" for d in week.days], now_col)

        if week.has_courses:
            self.hint.setText("Double-click a class for notes and homework, or an empty slot "
                              "to add an event.")
        else:
            self.hint.setText("No classes yet. Click “Courses & timetable…” to add your subjects "
                              "and when they meet. Double-click anywhere to add an event.")

    def _block_activated(self, item: AgendaItem, pos):
        if item.kind is ItemKind.EVENT:
            EventDialog(self.services, item.ref_id, parent=self).exec()
        else:
            class_menu(self, self.services, item.ref_id, item.day, pos, self.openClassNote.emit)

    def _empty_activated(self, col, minute):
        EventDialog(self.services, day=self.days[col], start=minute, parent=self).exec()
