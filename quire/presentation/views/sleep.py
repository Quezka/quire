"""Sleep log: last night, the goal, and the last two weeks at a glance."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDateEdit, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTimeEdit, QToolTip, QVBoxLayout, QWidget,
)

from ...application.bus import Topic
from ...application.inputs import SleepInput
from ...application.records import SleepOverview
from ...application.services import Services
from .. import theme
from ..bridge import ChangeRelay
from ..dialogs import attempt, to_qdate
from ..formatting import fmt_duration, fmt_min, long_date
from ..i18n import _
from ..notify import notify
from ..widgets import min_to_qtime, qtime_to_min
from .common import Card, Page, label, primary_button, scrolling


class SleepBars(QWidget):
    """One slot per day, with the goal as a line: a night not logged leaves a gap, so the days stay
    where they are. Press a night to open it in the form."""

    dayPicked = Signal(object)  # date

    def __init__(self, parent=None):
        super().__init__(parent)
        self.overview: SleepOverview | None = None
        self.selected = None
        self.setMinimumHeight(170)
        self.setCursor(Qt.PointingHandCursor)

    def set_overview(self, overview: SleepOverview):
        self.overview = overview
        self.update()

    def set_selected(self, day):
        self.selected = day
        self.update()

    def _slot_at(self, x: float):
        days = self.overview.days if self.overview else ()
        if not days or self.width() <= 0:
            return None
        return days[min(len(days) - 1, max(0, int(x / self.width() * len(days))))]

    def mousePressEvent(self, event):  # noqa: N802 (Qt naming)
        slot = self._slot_at(event.position().x())
        if slot is not None:
            self.dayPicked.emit(slot[0])

    def event(self, event):
        if event.type() == QEvent.ToolTip:
            slot = self._slot_at(event.position().x() if hasattr(event, "position") else event.x())
            if slot is not None:
                day, night = slot
                text = long_date(day)
                if night is not None:
                    text += "\n" + _("Slept {time}").format(time=fmt_duration(night.minutes))
                    text += f" ({fmt_min(night.asleep)}\u2013{fmt_min(night.woke)})"
                QToolTip.showText(event.globalPos(), text, self)
            return True
        return super().event(event)

    def paintEvent(self, _event):
        o = self.overview
        if o is None or not o.days:
            return
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        top = max([o.goal_hours * 60 + 60] + [n.minutes + 30 for n in o.nights])
        height = self.height() - 22
        width = self.width()
        slot = width / len(o.days)
        goal_y = height - o.goal_hours * 60 / top * height
        p.setPen(QPen(QColor(t.muted), 1, Qt.DashLine))
        p.drawLine(0, int(goal_y), width, int(goal_y))
        for i, (day, night) in enumerate(o.days):
            if day == self.selected:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(t.accent_soft))
                p.drawRoundedRect(QRectF(i * slot + 1, 0, slot - 2, self.height()), 6, 6)
            if night is not None:
                bar = night.minutes / top * height
                enough = night.minutes >= o.goal_hours * 60 * 0.9
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(t.accent if enough else t.danger))
                p.drawRoundedRect(QRectF(i * slot + slot * 0.2, height - bar, slot * 0.6, bar), 5, 5)
            font = p.font()
            font.setBold(i == len(o.days) - 1)
            p.setFont(font)
            p.setPen(QColor(t.text if i == len(o.days) - 1 else t.muted))
            p.drawText(QRectF(i * slot, height + 2, slot, 18), Qt.AlignCenter, str(day.day))
        p.end()


class SleepView(Page):
    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.sleep = services.sleep
        self.planner = services.planner
        self.title.setText(_("Sleep"))

        # ---- one tap: going to sleep / awake ----
        self.now_status = label("", "muted")
        self.now_status.setWordWrap(True)
        self.sleep_btn = primary_button(_("I'm going to sleep"), "moon")
        self.sleep_btn.clicked.connect(self._going_to_sleep)
        self.awake_btn = primary_button(_("I'm awake"), None)
        self.awake_btn.clicked.connect(self._awake)
        self.cancel_btn = QPushButton(_("Cancel"))
        self.cancel_btn.clicked.connect(self.sleep.cancel_going_to_sleep)
        tap = QHBoxLayout()
        tap.addWidget(self.sleep_btn)
        tap.addWidget(self.awake_btn)
        tap.addWidget(self.cancel_btn)
        tap.addStretch()
        tonight = Card(_("Tonight"))
        tonight.add(self.now_status)
        tonight.body.addLayout(tap)
        self.last_night = label("", "muted")
        self.last_night.setWordWrap(True)
        tonight.add(self.last_night)
        self.rate_row = QWidget()
        rate = QHBoxLayout(self.rate_row)
        rate.setContentsMargins(0, 0, 0, 0)
        rate.addWidget(label(_("How did you sleep?")))
        for n in range(1, 6):
            button = QPushButton(str(n))
            button.setToolTip(_("1 is awful, 5 is great"))
            button.clicked.connect(lambda _checked=False, n=n: self._rate(n))
            rate.addWidget(button)
        rate.addStretch()
        tonight.add(self.rate_row)

        # ---- the night ----
        self.date = QDateEdit(calendarPopup=True)
        self.date.setDisplayFormat("ddd d MMM yyyy")
        self.asleep = QTimeEdit(min_to_qtime(23 * 60), displayFormat="HH:mm")
        self.woke = QTimeEdit(min_to_qtime(7 * 60), displayFormat="HH:mm")
        self.note = QLineEdit(placeholderText=_("How was it? (optional)"))
        self.quality = QButtonGroup(self)
        stars = QHBoxLayout()
        for n in range(1, 6):
            button = QPushButton(str(n), checkable=True)
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
        self.remind = QCheckBox(_("Remind me before bedtime"), checked=self.sleep.remind_enabled())
        self.remind.toggled.connect(self.sleep.set_remind)
        goal_card.add(self.remind)

        # ---- the last nights ----
        self.bars = SleepBars()
        self.bars.dayPicked.connect(self._pick_day)
        self.summary = label("", "muted")
        self.summary.setWordWrap(True)
        chart_card = Card(_("Last two weeks"))
        chart_card.add(self.bars)
        chart_card.add(self.summary)

        left = QVBoxLayout()
        left.addWidget(tonight)
        left.addWidget(night_card)
        left.addWidget(goal_card)
        left.addStretch()
        row = QHBoxLayout()
        row.setSpacing(18)
        row.addLayout(left, 2)
        row.addWidget(chart_card, 3, Qt.AlignTop)
        self.root.addWidget(scrolling(row), 1)

        self._timer = QTimer(self, interval=60_000)  # the wind-down nudge, while Quire is open
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self.date.setDate(to_qdate(self.planner.today()))
        self.date.dateChanged.connect(self._load_night)
        relay.changed.connect(self._changed)
        self._load_goal()
        self.hours.valueChanged.connect(self._save_goal)  # at once: arrows and wheel count as well
        self.wake_goal.timeChanged.connect(self._save_goal)
        self._load_night()
        self.refresh()
        theme.themed(lambda _t: self.refresh())  # the chart and its colours

    # ---- data ----

    def _changed(self, topic):
        if topic is Topic.SLEEP:
            self.refresh()

    def _tick(self):
        self._remind()
        if self.isVisible():
            self.refresh()  # the countdown to bedtime

    def _rate(self, quality: int):
        day = self.planner.today()
        attempt(self, lambda: self.sleep.rate(day, quality))
        if self.date.date().toPython() == day:
            self._load_night()

    def _pick_day(self, day):
        self.date.setDate(to_qdate(day))

    def _remind(self):
        bedtime = self.sleep.reminder()
        if bedtime is not None:
            notify(_("Time to wind down"), _("Aim to be asleep by {time}.").format(time=fmt_min(bedtime)))

    def _show_last_night(self, o):
        night = o.last_night
        self.rate_row.setVisible(night is not None and night.quality is None)
        lines = []
        if night is not None:
            line = _("Last night: {time} ({start} to {end}).").format(
                time=fmt_duration(night.minutes), start=fmt_min(night.asleep), end=fmt_min(night.woke))
            if night.quality:
                line += " " + _("Rated {value} of 5.").format(value=night.quality)
            lines.append(line)
        if o.asleep_since is None and o.bedtime_in <= 6 * 60:
            lines.append(_("Bedtime at {time}, in {left}.").format(
                time=fmt_min(o.bedtime_goal), left=fmt_duration(o.bedtime_in)))
        self.last_night.setText("\n".join(lines))
        self.last_night.setVisible(bool(lines))

    def _going_to_sleep(self):
        self.sleep.go_to_sleep()

    def _awake(self):
        if attempt(self, self.sleep.wake_up):
            self.date.setDate(to_qdate(self.planner.today()))
            self._load_night()

    def refresh(self):
        o = self.sleep.overview()
        asleep = o.asleep_since is not None
        self.sleep_btn.setVisible(not asleep)
        self.awake_btn.setVisible(asleep)
        self.cancel_btn.setVisible(asleep)
        self.now_status.setText(_("Asleep since {time}. Tap when you're up.").format(time=fmt_min(o.asleep_since))
                                if asleep else _("Tap when you go to bed, and again when you wake: no typing."))
        self.bars.set_overview(o)
        self._show_last_night(o)
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
        lines = [" · ".join(parts)]
        if o.regularity:
            lines.append({"steady": _("Your bedtimes are steady."),
                          "mixed": _("Your bedtimes wander a bit (about {m} min).").format(m=o.bedtime_spread),
                          "irregular": _("Your bedtimes are all over the place (about {m} min). A fixed time helps most.")
                          .format(m=o.bedtime_spread)}[o.regularity])
        if o.streak >= 2:
            lines.append(_("{n} nights in a row on goal.").format(n=o.streak))
        if o.last_week_average is not None:
            change = o.average_minutes - o.last_week_average
            if abs(change) >= 10:
                lines.append(_("{time} {more} a night than the week before.").format(
                    time=fmt_duration(abs(change)), more=_("more") if change > 0 else _("less")))
        if o.focus_after_enough is not None:
            lines.append(_("You focus {a} min on days after a full night, {b} min after a short one.").format(
                a=o.focus_after_enough, b=o.focus_after_short))
        self.summary.setText("\n".join(lines))

    def _load_goal(self):
        hours, wake = self.sleep.goal()
        self.hours.setValue(hours)
        self.wake_goal.setTime(min_to_qtime(wake))

    def _save_goal(self, *_ignored):
        self.sleep.save_goal(self.hours.value(), qtime_to_min(self.wake_goal.time()))

    def _load_night(self, *_ignored):
        day = self.date.date().toPython()
        self.bars.set_selected(day)
        night = self.sleep.night(day)
        checked = self.quality.checkedButton()
        if checked:
            self.quality.setExclusive(False)
            checked.setChecked(False)
            self.quality.setExclusive(True)
        if night is None:
            self.result.setText("")
            self.delete_btn.setVisible(False)
            self.note.clear()
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
