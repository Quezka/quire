"""Water tracking: the day's ring, quick buttons, and the profile the goal comes from."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QListWidget, QPushButton, QSpinBox,
    QTimeEdit, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.inputs import WaterProfileInput
from ...application.services import Services
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import attempt
from ..formatting import fmt_min
from ..i18n import _
from ..notify import notify
from ..widgets import ProgressRing, min_to_qtime, qtime_to_min
from .common import Card, Page, label, primary_button, scrolling


class WeekBars(QWidget):
    """The last seven days: one bar each, with the goal as a line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.week = ()
        self.goal = None
        self.setMinimumHeight(110)

    def set_data(self, week, goal):
        self.week, self.goal = week, goal
        self.update()

    def paintEvent(self, _event):
        if not self.week:
            return
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        top = max([self.goal or 0] + [ml for _day, ml in self.week] + [1]) * 1.1
        height = self.height() - 20
        slot = self.width() / len(self.week)
        if self.goal:
            y = height - self.goal / top * height
            p.setPen(QColor(t.border))
            p.drawLine(0, int(y), self.width(), int(y))
        for i, (day, ml) in enumerate(self.week):
            bar = ml / top * height
            reached = bool(self.goal) and ml >= self.goal
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.success if reached else t.accent))
            if bar > 0:
                p.drawRoundedRect(QRectF(i * slot + slot * 0.2, height - bar, slot * 0.6, bar), 5, 5)
            p.setPen(QColor(t.muted))
            p.drawText(QRectF(i * slot, height + 2, slot, 18), Qt.AlignCenter, str(day.day))
        p.end()


class WaterView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.water = services.water
        self.title.setText(_("Water"))

        # ---- today ----
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
        self.undo_btn.clicked.connect(self.water.undo_last)
        add_row.addWidget(self.undo_btn)
        add_row.addStretch()
        self.entries = QListWidget()
        self.entries.setMaximumHeight(110)
        today = Card()
        today.add(self.ring, 1)
        today.add(self.status)
        today.body.addLayout(add_row)
        today.add(self.entries)

        # ---- profile ----
        self.height_box = QDoubleSpinBox(minimum=80, maximum=250, decimals=0, singleStep=1)
        self.height_box.setSuffix(" cm")
        self.weight_box = QDoubleSpinBox(minimum=20, maximum=300, decimals=1, singleStep=0.5)
        self.weight_box.setSuffix(" kg")
        self.glass_box = QSpinBox(minimum=50, maximum=1000, singleStep=50)
        self.glass_box.setSuffix(" ml")
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
        form.addRow("", self.remind)
        form.addRow(_("Between"), hours)
        profile = Card(_("Your goal"))
        profile.body.addLayout(form)
        profile.add(self.goal_label)
        profile.add(save)

        self.bars = WeekBars()
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
        self.refresh()

        # Nudges while Quire is open: about once a minute, it checks whether you're behind.
        self._timer = QTimer(self, interval=60_000)
        self._timer.timeout.connect(self._remind)
        self._timer.start()

    # ---- data ----

    def _changed(self, topic):
        if topic is Topic.WATER:
            self.refresh()

    def _add(self, ml: int):
        attempt(self, lambda: self.water.add(ml))

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
        self.remind.setChecked(p.remind)
        self.start.setTime(min_to_qtime(p.start))
        self.end.setTime(min_to_qtime(p.end))

    def _save_profile(self):
        data = WaterProfileInput(self.height_box.value(), self.weight_box.value(),
                                 self.glass_box.value(), self.remind.isChecked(),
                                 qtime_to_min(self.start.time()), qtime_to_min(self.end.time()))
        attempt(self, lambda: self.water.save_profile(data))

    def refresh(self):
        o = self.water.overview()
        self.glass_btn.setText(f"+{o.profile.glass_ml} ml")
        self.undo_btn.setEnabled(bool(o.entries))
        self.bars.set_data(o.week, o.goal)
        t = theme.current()
        if o.goal is None:
            self.ring.set_state(0, "—", _("Set your height and weight"), t.accent, (0, 0))
            self.subtitle.setText(_("Set your height and weight to get a daily goal"))
            self.goal_label.setText(_("The goal comes from your body surface area, about 1.2 L per square metre."))
            self.status.setText("")
        else:
            self.ring.set_state(o.drunk / o.goal, f"{o.drunk} ml", _("of {goal} ml").format(goal=o.goal),
                                t.success if o.drunk >= o.goal else t.accent, (0, 0))
            self.subtitle.setText(_("{left} ml to go").format(left=max(0, o.goal - o.drunk)) if o.drunk < o.goal
                                  else _("Goal reached. Nice."))
            behind = o.expected - o.drunk
            self.status.setText(_("About {ml} ml behind where you'd be by now.").format(ml=behind)
                                if behind >= 250 and o.drunk < o.goal else "")
            self.goal_label.setText(_("Daily goal: {goal} ml, from your body surface area. A rough guide, not "
                                      "medical advice.").format(goal=o.goal))
        self.entries.clear()
        for e in reversed(o.entries):
            self.entries.addItem(f"{fmt_min(e.at)}   +{e.ml} ml")
