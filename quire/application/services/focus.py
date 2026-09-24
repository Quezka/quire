from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ...domain import (
    FocusSession, FocusSettings, Phase, PhaseEnded, PomodoroTimer, Task,
)
from ..bus import ChangeBus, Topic
from ..dto import TaskItem
from ..ports import Clock, CourseRepository, FocusLogRepository, KeyValueStore, TaskRepository


@dataclass(frozen=True)
class FocusStats:
    today_sessions: int
    today_minutes: int
    week_sessions: int
    week_minutes: int


class FocusService:
    """Use cases for the Pomodoro focus timer.

    Holds the one running timer; the UI calls `tick()` about once a second.
    Finished focus sessions are logged (with the task you were on) for the stats.
    """

    PREFIX = "focus."

    def __init__(self, log: FocusLogRepository, settings: KeyValueStore,
                 tasks: TaskRepository, courses: CourseRepository, clock: Clock,
                 bus: ChangeBus):
        self._log = log
        self._settings = settings
        self._tasks = tasks
        self._courses = courses
        self._clock = clock
        self._bus = bus
        self.timer = PomodoroTimer(self.settings())

    # ---- settings ---------------------------------------------------------------

    def settings(self) -> FocusSettings:
        defaults = FocusSettings()
        def number(name, default):
            value = self._settings.get(self.PREFIX + name)
            return int(value) if value and value.isdigit() else default
        auto = self._settings.get(self.PREFIX + "auto_continue")
        return FocusSettings(
            number("work", defaults.work_minutes),
            number("short_break", defaults.short_break_minutes),
            number("long_break", defaults.long_break_minutes),
            number("rounds", defaults.rounds),
            defaults.auto_continue if auto is None else auto == "1")

    def save_settings(self, settings: FocusSettings):
        settings.validate()
        for name, value in (("work", settings.work_minutes),
                            ("short_break", settings.short_break_minutes),
                            ("long_break", settings.long_break_minutes),
                            ("rounds", settings.rounds)):
            self._settings.set(self.PREFIX + name, str(value))
        self._settings.set(self.PREFIX + "auto_continue", "1" if settings.auto_continue else "0")
        self.timer.apply_settings(settings)
        self._bus.publish(Topic.FOCUS)

    # ---- what you're focusing on ------------------------------------------------

    def focus_task(self) -> Task | None:
        value = self._settings.get(self.PREFIX + "task")
        task = self._tasks.get(int(value)) if value and value.isdigit() else None
        return task if task and not task.done else None

    def set_focus_task(self, task_id: int | None):
        self._settings.set(self.PREFIX + "task", None if task_id is None else str(task_id))

    def candidate_tasks(self, days: int = 14) -> list[TaskItem]:
        """Open tasks worth focusing on: overdue, due soon, or without a date."""
        today = self._clock.today()
        courses = {c.id: c for c in self._courses.list()}
        tasks = [t for t in self._tasks.list(include_done=False)
                 if t.due is None or (t.due - today).days <= days]
        tasks.sort(key=lambda t: (t.due is None, t.due or today, t.title.casefold()))
        return [TaskItem(t, courses.get(t.course_id), t.is_overdue(today)) for t in tasks]

    # ---- controls ---------------------------------------------------------------

    def now(self) -> datetime:
        return self._clock.now()

    def toggle(self):
        now = self._clock.now()
        (self.timer.pause if self.timer.running else self.timer.start)(now)

    def reset(self):
        self.timer.reset()

    def skip(self):
        self.timer.skip(self._clock.now())

    def tick(self) -> PhaseEnded | None:
        """Advance the timer; returns the phase that just ended, if any.

        After a long sleep several phases may have passed; they're all processed
        and the latest one is reported.
        """
        last = None
        while (event := self.timer.tick(self._clock.now())) is not None:
            last = event
            if event.phase is Phase.WORK:
                task = self.focus_task()
                self._log.add(FocusSession(event.started, event.minutes,
                                           task.id if task else None))
                self._bus.publish(Topic.FOCUS)
        return last

    # ---- stats ------------------------------------------------------------------

    def stats(self) -> FocusStats:
        today = self._clock.today()
        monday = today - timedelta(days=today.weekday())
        week = self._log.between(monday, monday + timedelta(days=6))
        todays = [s for s in week if s.started.date() == today]
        return FocusStats(len(todays), sum(s.minutes for s in todays),
                          len(week), sum(s.minutes for s in week))
