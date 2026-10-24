"""Sleep log: last night, the goal, and the last two weeks at a glance."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QButtonGroup, QDateEdit, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTimeEdit, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.inputs import SleepInput
from ...application.records import SleepOverview
from ...application.services import Services
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import attempt, to_qdate
from ..formatting import fmt_duration, fmt_min
from ..i18n import _
from ..widgets import min_to_qtime, qtime_to_min
from .common import Card, Page, label, primary_button


class SleepBars(QWidget):
    """One bar per night, with the goal as a line."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overview: SleepOverview | None = None
        self.setMinimumHeight(150)

    def set_overview(self, overview: SleepOverview):
        self.overview = overview
        self.update()

    def paintEvent(self, _event):
        o = self.overview
        if o is None:
            return
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        top = max([o.goal_hours * 60 + 60] + [n.minutes + 30 for n in o.nights])
        height = self.height() - 22
        width = self.width()
        goal_y = height - o.goal_hours * 60 / top * height
        p.setPen(QColor(t.border))
        p.drawLine(0, int(goal_y), width, int(goal_y))
        slot = width / max(1, len(o.nights))
        for i, night in enumerate(o.nights):
            bar = night.minutes / top * height
            enough = night.minutes >= o.goal_hours * 60 * 0.9
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.accent if enough else t.danger))
            p.drawRoundedRect(QRectF(i * slot + slot * 0.2, height - bar, slot * 0.6, bar), 5, 5)
            p.setPen(QColor(t.muted))
            p.drawText(QRectF(i * slot, height + 2, slot, 18), Qt.AlignCenter, str(night.day.day))
        p.end()


class SleepView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.sleep = services.sleep
        self.planner = services.planner
        self.title.setText(_("Sleep"))

        # ---- the night ----
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.asleep = QTimeEdit(min_to_qtime(23 * 60), displayFormat="HH:mm")
        self.woke = QTimeEdit(min_to_qtime(7 * 60), displayFormat="HH:mm")
        self.note = QLineEdit(placeholderText=_("How was it? (optional)"))
        self.quality = QButtonGroup(self)
        stars = QHBoxLayout()
        for n in range(1, 6):
            button = QPushButton(str(n), objectName="segment", checkable=True)
            button.setToolTip(_("1 is awful, 5 is great"))
            self.quality.addButton(button, n)
            stars.addWidget(button)
        stars.addStretch()
        self.quality.setExclusive(True)
        self.result = label("", "muted")
        self.save_btn = primary_button(_("Save night"), None)
        self.save_btn.clicked.connect(self._save)
        self.delete_btn = QPushButton(_("Delete"), objectName="danger")
        self.delete_btn.clicked.connect(self._delete)
        buttons = QHBoxLayout()
        buttons.addWidget(self.result, 1)
        buttons.addWidget(self.delete_btn)
        buttons.addWidget(self.save_btn)
        form = QFormLayout()
        form.addRow(_("Woke up on"), self.date)
        form.addRow(_("Fell asleep"), self.asleep)
        form.addRow(_("Woke up"), self.woke)
        form.addRow(_("Quality"), stars)
        form.addRow(_("Note"), self.note)
        night_card = Card(_("Log a night"))
        night_card.body.addLayout(form)
        night_card.body.addLayout(buttons)

        # ---- the goal ----
        self.hours = QDoubleSpinBox(minimum=3.0, maximum=14.0, singleStep=0.5, decimals=1)
        self.hours.setSuffix(_(" h"))
        self.wake_goal = QTimeEdit(displayFormat="HH:mm")
        self.bedtime = label("", "muted")
        goal_form = QFormLayout()
        goal_form.addRow(_("Hours of sleep"), self.hours)
        goal_form.addRow(_("Wake up at"), self.wake_goal)
        goal_card = Card(_("Goal"))
        goal_card.body.addLayout(goal_form)
        goal_card.add(self.bedtime)

        # ---- the last nights ----
        self.bars = SleepBars()
        self.summary = label("", "muted")
        self.summary.setWordWrap(True)
        chart_card = Card(_("Last two weeks"))
        chart_card.add(self.bars)
        chart_card.add(self.summary)

        left = QVBoxLayout()
        left.addWidget(night_card)
        left.addWidget(goal_card)
        left.addStretch()
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addLayout(left, 2)
        row.addWidget(chart_card, 3, Qt.AlignTop)
        self.root.addLayout(row, 1)

        self.date.setDate(to_qdate(self.planner.today()))
        self.date.dateChanged.connect(self._load_night)
        self.hours.editingFinished.connect(self._save_goal)
        self.wake_goal.editingFinished.connect(self._save_goal)
        relay.changed.connect(self._changed)
        self._load_goal()
        self._load_night()
        self.refresh()

    # ---- data ----

    def _changed(self, topic):
        if topic is Topic.SLEEP:
            self.refresh()

    def refresh(self):
        o = self.sleep.overview()
        self.bars.set_overview(o)
        self.bedtime.setText(_("Be asleep by {time} to wake at {wake}.").format(
            time=fmt_min(o.bedtime_goal), wake=fmt_min(o.wake_goal)))
        if not o.nights:
            self.subtitle.setText(_("Log last night to start"))
            self.summary.setText(_("Nothing logged in the last two weeks."))
            return
        self.subtitle.setText(_("Average {time} a night").format(time=fmt_duration(o.average_minutes)))
        parts = [_("{enough} of {count} nights reached your goal").format(
            enough=o.enough, count=len(o.nights))]
        if o.shortfall_minutes:
            parts.append(_("{time} short in total").format(time=fmt_duration(o.shortfall_minutes)))
        if o.average_bedtime is not None:
            parts.append(_("usually asleep around {time}").format(time=fmt_min(o.average_bedtime)))
        if o.average_quality is not None:
            parts.append(_("average quality {value:.1f} of 5").format(value=o.average_quality))
        self.summary.setText(" · ".join(parts))

    def _load_goal(self):
        hours, wake = self.sleep.goal()
        self.hours.setValue(hours)
        self.wake_goal.setTime(min_to_qtime(wake))

    def _save_goal(self):
        self.sleep.save_goal(self.hours.value(), qtime_to_min(self.wake_goal.time()))

    def _load_night(self, *_ignored):
        night = self.sleep.night(self.date.date().toPython())
        if night is None:
            self.result.setText("")
            self.delete_btn.setVisible(False)
            self.note.clear()
            checked = self.quality.checkedButton()
            if checked:
                self.quality.setExclusive(False)
                checked.setChecked(False)
                self.quality.setExclusive(True)
            return
        self.asleep.setTime(min_to_qtime(night.asleep))
        self.woke.setTime(min_to_qtime(night.woke))
        self.note.setText(night.note)
        if night.quality:
            self.quality.button(night.quality).setChecked(True)
        self.delete_btn.setVisible(True)
        self.result.setText(_("Slept {time}").format(time=fmt_duration(night.minutes)))

    def _save(self):
        quality = self.quality.checkedId()
        data = SleepInput(self.date.date().toPython(), qtime_to_min(self.asleep.time()),
                          qtime_to_min(self.woke.time()), quality if quality > 0 else None,
                          self.note.text())
        if attempt(self, lambda: self.sleep.save(data)):
            self._load_night()

    def _delete(self):
        self.sleep.delete(self.date.date().toPython())
        self._load_night()
