"""Water tracking: the day's ring, quick buttons, and the profile the goal comes from."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.inputs import WaterProfileInput
from ...application.services import Services
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import attempt
from ..formatting import fmt_min, long_date
from ..i18n import _
from ..notify import notify
from ..widgets import ProgressRing, min_to_qtime, qtime_to_min
from .common import Card, Page, label, primary_button, scrolling
from quezka_ui.fit import exec_menu


class WeekBars(QWidget):
    """The last seven days: one bar each with its amount, the goal as a line. Press a day to see it."""

    dayPicked = Signal(object)  # date

    def __init__(self, parent=None):
        super().__init__(parent)
        self.week = ()
        self.goal = None
        self.selected = None
        self.setMinimumHeight(140)
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, week, goal, selected=None):
        self.week, self.goal, self.selected = week, goal, selected
        self.update()

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        if self.week and self.width() > 0:
            i = int(event.position().x() / self.width() * len(self.week))
            self.dayPicked.emit(self.week[min(len(self.week) - 1, max(0, i))][0])

    def paintEvent(self, _event):
        if not self.week:
            return
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        top = max([self.goal or 0] + [ml for _day, ml in self.week] + [1]) * 1.1
        height = self.height() - 20
        chart = height - 18  # room for the amount over the tallest bar
        slot = self.width() / len(self.week)
        if self.goal:
            y = height - self.goal / top * chart
            p.setPen(QPen(QColor(t.muted), 1, Qt.DashLine))
            p.drawLine(0, int(y), self.width(), int(y))
        for i, (day, ml) in enumerate(self.week):
            if day == self.selected:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(t.accent_soft))
                p.drawRoundedRect(QRectF(i * slot + 1, 0, slot - 2, self.height()), 6, 6)
            bar = ml / top * chart
            reached = bool(self.goal) and ml >= self.goal
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.success if reached else t.accent))
            if bar > 0:
                p.drawRoundedRect(QRectF(i * slot + slot * 0.2, height - bar, slot * 0.6, bar), 5, 5)
                p.setPen(QColor(t.text))
                p.drawText(QRectF(i * slot, height - bar - 18, slot, 18), Qt.AlignCenter, f"{ml / 1000:.1f}")
            font = p.font()
            font.setBold(i == len(self.week) - 1)
            p.setFont(font)
            p.setPen(QColor(t.text if i == len(self.week) - 1 else t.muted))
            p.drawText(QRectF(i * slot, height + 2, slot, 18), Qt.AlignCenter, str(day.day))
            font.setBold(False)
            p.setFont(font)
        p.end()


class WaterView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.water = services.water
        self.planner = services.planner
        self.title.setText(_("Water"))

        # ---- today ----
        self._shown = None  # the day on show; None is today
        self.day_label = label("", "muted")
        self.day_label.setAlignment(Qt.AlignCenter)
        self.today_btn = QPushButton(_("Back to today"))
        self.today_btn.clicked.connect(lambda: self._pick_day(self.planner.today()))
        day_row = QHBoxLayout()
        day_row.addStretch()
        day_row.addWidget(self.day_label)
        day_row.addWidget(self.today_btn)
        day_row.addStretch()
        self.ring = ProgressRing()
        self.status = label("", "muted")
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setWordWrap(True)
        add_row = QHBoxLayout()
        add_row.addStretch()
        self.glass_btn = primary_button("", None)
        self.glass_btn.clicked.connect(lambda: self._add(self.water.profile().glass_ml))
        add_row.addWidget(self.glass_btn)
        for ml in (150, 500):
            button = QPushButton(f"+{ml} ml")
            button.clicked.connect(lambda _checked=False, ml=ml: self._add(ml))
            add_row.addWidget(button)
        self.undo_btn = QPushButton(_("Undo"))
        self.undo_btn.clicked.connect(lambda: self.water.undo_last(self._shown))
        add_row.addWidget(self.undo_btn)
        add_row.addStretch()
        self.amount = QSpinBox(minimum=10, maximum=2000, singleStep=10, value=330)
        self.amount.setSuffix(" ml")
        self.amount.setToolTip(_("Any other amount"))
        self.amount.setAccessibleName(_("Any other amount"))
        add_amount = QPushButton(_("Add"))
        add_amount.clicked.connect(lambda: self._add(self.amount.value()))
        other_row = QHBoxLayout()
        other_row.addStretch()
        other_row.addWidget(self.amount)
        other_row.addWidget(add_amount)
        other_row.addStretch()
        self.stats = label("", "muted")
        self.stats.setAlignment(Qt.AlignCenter)
        self.stats.setWordWrap(True)
        self.entries = QListWidget()
        self.entries.setMaximumHeight(130)
        self.entries.setToolTip(_("Right-click an entry to remove it"))
        self.entries.setContextMenuPolicy(Qt.CustomContextMenu)
        self.entries.customContextMenuRequested.connect(self._entry_menu)
        today = Card()
        today.body.addLayout(day_row)
        today.add(self.ring, 1)
        today.add(self.status)
        today.body.addLayout(add_row)
        today.body.addLayout(other_row)
        today.add(self.stats)
        today.add(self.entries)

        # ---- profile ----
        self.height_box = QDoubleSpinBox(minimum=80, maximum=250, decimals=0, singleStep=1)
        self.height_box.setSuffix(" cm")
        self.weight_box = QDoubleSpinBox(minimum=20, maximum=300, decimals=1, singleStep=0.5)
        self.weight_box.setSuffix(" kg")
        self.glass_box = QSpinBox(minimum=50, maximum=1000, singleStep=50)
        self.glass_box.setSuffix(" ml")
        self.goal_box = QSpinBox(minimum=0, maximum=6000, singleStep=100)
        self.goal_box.setSuffix(" ml")
        self.goal_box.setSpecialValueText(_("From height and weight"))
        self.remind = QCheckBox(_("Remind me when I fall behind"))
        self.start = QTimeEdit(displayFormat="HH:mm")
        self.end = QTimeEdit(displayFormat="HH:mm")
        self.goal_label = label("", "muted")
        self.goal_label.setWordWrap(True)
        save = primary_button(_("Save"), None)
        save.clicked.connect(self._save_profile)
        hours = QHBoxLayout()
        hours.addWidget(self.start)
        hours.addWidget(label(_("to")))
        hours.addWidget(self.end)
        hours.addStretch()
        form = QFormLayout()
        form.addRow(_("Height"), self.height_box)
        form.addRow(_("Weight"), self.weight_box)
        form.addRow(_("One glass"), self.glass_box)
        form.addRow(_("Daily goal"), self.goal_box)
        form.addRow("", self.remind)
        form.addRow(_("Between"), hours)
        profile = Card(_("Your goal"))
        profile.body.addLayout(form)
        profile.add(self.goal_label)
        profile.add(save)

        self.bars = WeekBars()
        self.bars.dayPicked.connect(self._pick_day)
        week = Card(_("Last seven days"))
        week.add(self.bars)

        right = QVBoxLayout()
        right.addWidget(profile)
        right.addWidget(week)
        right.addStretch()
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addWidget(today, 3)
        row.addLayout(right, 2)
        self.root.addWidget(scrolling(row), 1)

        relay.changed.connect(self._changed)
        self._load_profile()
        self._day = self.planner.today()
        theme.themed(lambda _t: self.refresh())  # also the first time: the ring's colours follow the theme

        # Nudges while Quire is open: about once a minute, it checks whether you're behind.
        self._timer = QTimer(self, interval=60_000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ---- data ----

    def _changed(self, topic):
        if topic is Topic.WATER:
            self.refresh()

    def _tick(self):
        """Quire stays open for days: at midnight today's count starts again by itself."""
        if self.planner.today() != self._day:
            self._day = self.planner.today()
            self._shown = None
            self.refresh()
        self._remind()

    def showEvent(self, event):  # noqa: N802 (Qt naming)
        super().showEvent(event)
        if self.planner.today() != self._day:
            self._tick()

    def _entry_menu(self, pos):
        item = self.entries.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        remove = menu.addAction(_("Remove this entry"))
        if exec_menu(menu, self.entries.viewport().mapToGlobal(pos)) is remove:
            self.water.delete(item.data(Qt.UserRole))

    def _pick_day(self, day):
        self._shown = None if day == self.planner.today() else day
        self.refresh()

    def _add(self, ml: int):
        attempt(self, lambda: self.water.add(ml, self._shown))

    def _remind(self):
        line = self.water.reminder()
        if line:
            drunk, goal = line.split("/")
            notify(_("Time for some water"), _("You've had {drunk} of {goal} ml today.").format(
                drunk=drunk, goal=goal))

    def _load_profile(self):
        p = self.water.profile()
        self.height_box.setValue(p.height_cm or 170)
        self.weight_box.setValue(p.weight_kg or 65)
        self.glass_box.setValue(p.glass_ml)
        self.goal_box.setValue(p.manual_goal or 0)
        self.remind.setChecked(p.remind)
        self.start.setTime(min_to_qtime(p.start))
        self.end.setTime(min_to_qtime(p.end))

    def _save_profile(self):
        data = WaterProfileInput(self.height_box.value(), self.weight_box.value(),
                                 self.glass_box.value(), self.remind.isChecked(),
                                 qtime_to_min(self.start.time()), qtime_to_min(self.end.time()),
                                 self.goal_box.value() or None)
        attempt(self, lambda: self.water.save_profile(data))

    def refresh(self):
        o = self.water.overview(self._shown)
        past = self._shown is not None
        self.day_label.setVisible(past)
        self.today_btn.setVisible(past)
        if past:
            self.day_label.setText(long_date(self._shown))
        self.glass_btn.setText(f"+{o.profile.glass_ml} ml")
        self.undo_btn.setEnabled(bool(o.entries))
        self.bars.set_data(o.week, o.goal, o.day)
        t = theme.current()
        if o.goal is None:
            self.ring.set_state(0, "—", _("Set your height and weight"), t.accent, (0, 0))
            self.subtitle.setText(_("Set your height and weight to get a daily goal"))
            self.goal_label.setText(_("The goal comes from your body surface area, about 1.2 L per square metre."))
            self.status.setText("")
        else:
            self.ring.set_state(o.drunk / o.goal, f"{o.drunk} ml", _("of {goal} ml").format(goal=o.goal),
                                t.success if o.drunk >= o.goal else t.accent, (0, 0))
            self.subtitle.setText(_("Goal reached. Nice.") if o.drunk >= o.goal else
                                  _("{left} ml to go").format(left=o.goal - o.drunk))
            behind = o.expected - o.drunk
            self.status.setText(_("About {ml} ml behind where you'd be by now.").format(ml=behind)
                                if behind >= 250 and o.drunk < o.goal else "")
            self.goal_label.setText(_("Daily goal: {goal} ml, chosen by you.").format(goal=o.goal)
                                    if o.profile.manual_goal else
                                    _("Daily goal: {goal} ml, from your body surface area. A rough guide, not "
                                      "medical advice.").format(goal=o.goal))
        parts = [_("{ml} ml a day this week").format(ml=o.average)] if o.average else []
        if o.goal:
            parts.append(_("{n} of the last 7 days on goal").format(n=o.on_goal))
        if o.streak >= 2:
            parts.insert(0, _("{days} days in a row").format(days=o.streak))
        self.stats.setText(" · ".join(parts))
        self.entries.clear()
        for e in reversed(o.entries):
            item = QListWidgetItem(f"{fmt_min(e.at)}   +{e.ml} ml")
            item.setData(Qt.UserRole, e.id)
            self.entries.addItem(item)
