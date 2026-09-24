"""Pomodoro focus timer, in the spirit of KDE's Francis."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel, QVBoxLayout

from ...application.bus import Topic
from ...application.errors import ApplicationError
from ...application.services import Services
from ...domain import DomainError, FocusSettings, Phase
from .. import icons, theme
from ..bridge import ChangeRelay
from ..formatting import fmt_duration, plural
from ..notify import notify
from ..widgets import ProgressRing, SpinBox, color_icon
from .common import Card, Page, button, icon_button, label, primary_button

PHASE_LABELS = {Phase.WORK: "Focus", Phase.SHORT_BREAK: "Short break",
                Phase.LONG_BREAK: "Long break"}


def phase_color(phase: Phase, t) -> str:
    return {Phase.WORK: t.accent, Phase.SHORT_BREAK: t.success,
            Phase.LONG_BREAK: "#12a594"}[phase]


def clock_text(seconds: float) -> str:
    seconds = int(round(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class FocusView(Page):
    # Remaining time while running ("24:13"), or "" when stopped; for the sidebar.
    statusChanged = Signal(str)

    def __init__(self, services: Services, relay: ChangeRelay, parent=None):
        super().__init__(parent)
        self.services = services
        self.focus = services.focus
        self.title.setText("Focus")

        # ---- timer ----
        self.ring = ProgressRing()
        self.start_btn = primary_button("Start", "play")
        self.start_btn.setMinimumWidth(130)
        self.start_btn.clicked.connect(self._toggle)
        reset = icon_button("reset", "Reset the cycle")
        reset.clicked.connect(self._reset)
        skip = icon_button("skip", "Skip to the next phase")
        skip.clicked.connect(self._skip)
        controls = QHBoxLayout()
        controls.addStretch()
        controls.addWidget(reset)
        controls.addWidget(self.start_btn)
        controls.addWidget(skip)
        controls.addStretch()

        self.task = QComboBox()
        self.task.setMinimumWidth(260)
        self.task.currentIndexChanged.connect(self._task_picked)
        task_row = QHBoxLayout()
        task_row.addStretch()
        task_row.addWidget(label("Focusing on", "muted"))
        task_row.addWidget(self.task)
        task_row.addStretch()

        timer_card = Card(padding=24)
        timer_card.add(self.ring, 1)
        timer_card.body.addLayout(controls)
        timer_card.body.addSpacing(6)
        timer_card.body.addLayout(task_row)

        # ---- stats ----
        stats = Card("Today")
        self.today_value = QLabel(objectName="tileValue")
        self.today_detail = label()
        self.week_detail = label()
        for widget in (self.today_value, self.today_detail, self.week_detail):
            stats.add(widget)

        # ---- settings ----
        settings = Card("Timer")
        self.work_min = SpinBox(minimum=1, maximum=180, suffix=" min")
        self.short_min = SpinBox(minimum=1, maximum=60, suffix=" min")
        self.long_min = SpinBox(minimum=1, maximum=120, suffix=" min")
        self.rounds = SpinBox(minimum=1, maximum=12)
        self.auto = QCheckBox("Start the next phase automatically")
        form = QFormLayout()
        form.addRow("Focus", self.work_min)
        form.addRow("Short break", self.short_min)
        form.addRow("Long break", self.long_min)
        form.addRow("Rounds before a long break", self.rounds)
        form.addRow("", self.auto)
        settings.body.addLayout(form)
        self.settings_hint = label("", "hint")
        self.settings_hint.setWordWrap(True)
        settings.add(self.settings_hint)
        self._load_settings()
        for box in (self.work_min, self.short_min, self.long_min, self.rounds):
            box.valueChanged.connect(self._save_settings)
        self.auto.toggled.connect(self._save_settings)

        side = QVBoxLayout()
        side.setSpacing(16)
        side.addWidget(stats)
        side.addWidget(settings)
        side.addStretch()

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(timer_card, 3)
        body.addLayout(side, 2)
        self.root.addLayout(body, 1)

        self._icon_state = None
        self._status = None
        self._ticker = QTimer(self, interval=250, timeout=self._tick)
        self._ticker.start()
        relay.changed.connect(self._changed)
        theme.manager().changed.connect(self._theme_changed)
        self._fill_tasks()
        self._render()
        self._render_stats()

    # ---- controls ---------------------------------------------------------------

    def _toggle(self):
        self.focus.toggle()
        self._render()

    def _reset(self):
        self.focus.reset()
        self._render()

    def _skip(self):
        self.focus.skip()
        self._render()

    def _tick(self):
        event = self.focus.tick()
        if event is not None:
            nxt = PHASE_LABELS[event.next_phase].lower()
            if event.phase is Phase.WORK:
                notify("Focus session done", f"Nice work. Time for a {nxt}.")
            else:
                notify("Break's over", "Ready for the next focus session?")
            self._render_stats()
        self._render()

    # ---- rendering ----------------------------------------------------------------

    def _render(self):
        t = theme.current()
        timer = self.focus.timer
        now = self.focus.now()
        remaining = timer.remaining(now).total_seconds()
        color = phase_color(timer.phase, t)
        done = timer.completed if timer.phase is Phase.WORK else min(
            timer.completed, timer.settings.rounds)
        self.ring.set_state(timer.progress(now), clock_text(remaining),
                            PHASE_LABELS[timer.phase], color, (done, timer.settings.rounds))
        running = timer.running
        self.start_btn.setText("Pause" if running else "Resume" if timer.started else "Start")
        icon = "pause" if running else "play"
        if icon != self._icon_state:  # set_icon registers a theme listener: only on change
            self._icon_state = icon
            self.start_btn.setIcon(icons.icon(icon, theme.current().on_accent, size=16))
        phase = PHASE_LABELS[timer.phase]
        self.subtitle.setText(
            f"{phase} · round {timer.round} of {timer.settings.rounds}"
            + ("" if running else " · paused" if timer.started else ""))
        status = clock_text(remaining) if running else ""
        if status != self._status:
            self._status = status
            self.statusChanged.emit(status)

    def _theme_changed(self, _theme):
        self._icon_state = None  # recolour the start button's icon
        self._render()

    def _render_stats(self):
        s = self.focus.stats()
        self.today_value.setText(plural(s.today_sessions, "pomodoro"))
        self.today_detail.setText(f"{fmt_duration(s.today_minutes)} of focus"
                                  if s.today_minutes else "No focus sessions yet today")
        self.week_detail.setText(f"This week: {plural(s.week_sessions, 'pomodoro')}, "
                                 f"{fmt_duration(s.week_minutes)}" if s.week_minutes else "")

    # ---- tasks ------------------------------------------------------------------

    def _changed(self, topic: Topic):
        if topic in (Topic.TASKS, Topic.COURSES):
            self._fill_tasks()
        if topic is Topic.FOCUS:
            self._render_stats()

    def _fill_tasks(self):
        current = self.focus.focus_task()
        self.task.blockSignals(True)
        self.task.clear()
        self.task.addItem("Nothing in particular", None)
        for entry in self.focus.candidate_tasks():
            text = entry.task.title + (f"  ·  {entry.course.name}" if entry.course else "")
            if entry.course:
                self.task.addItem(color_icon(entry.course.color), text, entry.task.id)
            else:
                self.task.addItem(text, entry.task.id)
        index = self.task.findData(current.id) if current else 0
        self.task.setCurrentIndex(max(index, 0))
        self.task.blockSignals(False)

    def _task_picked(self):
        self.focus.set_focus_task(self.task.currentData())

    # ---- settings ---------------------------------------------------------------

    def _load_settings(self):
        s = self.focus.settings()
        for box, value in ((self.work_min, s.work_minutes), (self.short_min, s.short_break_minutes),
                           (self.long_min, s.long_break_minutes), (self.rounds, s.rounds)):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self.auto.blockSignals(True)
        self.auto.setChecked(s.auto_continue)
        self.auto.blockSignals(False)

    def _save_settings(self):
        settings = FocusSettings(self.work_min.value(), self.short_min.value(),
                                 self.long_min.value(), self.rounds.value(),
                                 self.auto.isChecked())
        try:
            self.focus.save_settings(settings)
        except (DomainError, ApplicationError) as e:
            self.settings_hint.setText(str(e))
            return
        self.settings_hint.setText("New durations apply from the next phase."
                                   if self.focus.timer.started else "")
        self._render()
