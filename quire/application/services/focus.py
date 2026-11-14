from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ...domain import Event, FocusSession, FocusSettings, Phase, PomodoroTimer, Task, TimeRange
from ...domain.focus import plan_block
from ..bus import ChangeBus, Topic
from ..dto import TaskItem
from ..records import (
    FocusEvent, FocusSettingsData, FocusState, TaskRecord, course_record, focus_settings_data,
    task_record,
)
from ..ports import Clock, CourseRepository, EventRepository, FocusLogRepository, KeyValueStore, TaskRepository


@dataclass(frozen=True)
class FocusStats:
    today_sessions: int
    today_minutes: int
    week_sessions: int
    week_minutes: int
    today_by_project: tuple[tuple[str, int], ...] = ()  # (task or project, minutes), most first


class FocusService:
    """Use cases for the Pomodoro focus timer.

    Holds the one running timer; the UI calls `tick()` about once a second.
    Focus sessions are logged (with the task you were on) for the stats; one skipped or
    reset part-way is logged too, as unfinished, so its minutes still count.
    """

    PREFIX = "focus."

    def __init__(self, log: FocusLogRepository, settings: KeyValueStore,
                 tasks: TaskRepository, courses: CourseRepository, clock: Clock,
                 bus: ChangeBus, events: EventRepository | None = None):
        self._log = log
        self._settings = settings
        self._tasks = tasks
        self._courses = courses
        self._clock = clock
        self._bus = bus
        self._events = events
        self._timer = PomodoroTimer(self._load_settings())

    # ---- settings ---------------------------------------------------------------

    def settings(self) -> FocusSettingsData:
        return focus_settings_data(self._load_settings())

    def _load_settings(self) -> FocusSettings:
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

    def save_settings(self, data: FocusSettingsData):
        settings = FocusSettings(data.work_minutes, data.short_break_minutes,
                                 data.long_break_minutes, data.rounds, data.auto_continue)
        settings.validate()
        for name, value in (("work", settings.work_minutes),
                            ("short_break", settings.short_break_minutes),
                            ("long_break", settings.long_break_minutes),
                            ("rounds", settings.rounds)):
            self._settings.set(self.PREFIX + name, str(value))
        self._settings.set(self.PREFIX + "auto_continue", "1" if settings.auto_continue else "0")
        self._timer.apply_settings(settings)
        self._bus.publish(Topic.FOCUS)

    # ---- what you're focusing on ------------------------------------------------

    def _focus_task(self) -> Task | None:
        value = self._settings.get(self.PREFIX + "task")
        task = self._tasks.get(int(value)) if value and value.isdigit() else None
        return task if task and not task.done else None

    def focus_task(self) -> TaskRecord | None:
        task = self._focus_task()
        return task_record(task) if task else None

    def set_focus_task(self, task_id: int | None):
        self._settings.set(self.PREFIX + "task", None if task_id is None else str(task_id))
        self._settings.set(self.PREFIX + "project", None)

    def focus_project(self) -> str:
        """The ad-hoc project you're on, when it isn't one of your tasks ("" for none)."""
        return self._settings.get(self.PREFIX + "project") or ""

    def set_focus_project(self, name: str):
        """Focus on something that isn't a task, e.g. a side project; "" for nothing."""
        name = " ".join(name.split())
        self._settings.set(self.PREFIX + "project", name or None)
        self._settings.set(self.PREFIX + "task", None)

    def recent_projects(self, limit: int = 8) -> list[str]:
        return self._log.recent_labels(limit)

    def candidate_tasks(self, days: int = 14) -> list[TaskItem]:
        """Open tasks worth focusing on: overdue, due soon, or without a date."""
        today = self._clock.today()
        courses = {c.id: course_record(c) for c in self._courses.list()}
        tasks = [t for t in self._tasks.list(include_done=False)
                 if t.due is None or (t.due - today).days <= days]
        tasks.sort(key=lambda t: (t.due is None, t.due or today, t.title.casefold()))
        return [TaskItem(task_record(t), courses.get(t.course_id), t.is_overdue(today))
                for t in tasks]

    # ---- controls ---------------------------------------------------------------

    def now(self) -> datetime:
        return self._clock.now()

    def state(self) -> FocusState:
        """A snapshot of the timer, for showing it."""
        timer, now = self._timer, self._clock.now()
        block_left = (max(0.0, (timer.block_ends - now).total_seconds()) if timer.block_ends else None)
        return FocusState(timer.phase, timer.remaining(now).total_seconds(), timer.progress(now),
                          timer.running, timer.started, timer.round, timer.settings.rounds,
                          timer.completed, block_left)

    BLOCK_COLOR = "#4f46e5"

    def block_plan(self, total_minutes: int) -> list[tuple[Phase, int]]:
        """How a focus block of that length would run (focus and breaks), for showing before it starts."""
        return plan_block(total_minutes, self._timer.settings)

    def start_block(self, total_minutes: int):
        """Focus for a set time (2 hours, say): rounds and breaks run by themselves, and when the block ends it
        goes into the week as an event."""
        self._log_cut_short()
        self._end_block()
        self._timer.start_block(self._clock.now(), total_minutes)
        self._bus.publish(Topic.FOCUS)

    def _end_block(self, until: datetime | None = None):
        """The block (if one is on) goes into the planner as an event, from its start to `until` (now)."""
        started = self._timer.block_started
        if started is None:
            return
        end = until or self._clock.now()
        self._timer.block_started = self._timer.block_ends = None
        self._add_block_event(started, end)

    def _add_block_event(self, started: datetime, end: datetime):
        if self._events is None or end - started < timedelta(minutes=1):
            return
        first = started.hour * 60 + started.minute
        last = end.hour * 60 + end.minute if end.date() == started.date() else 24 * 60
        if last <= first:
            return
        task = self._focus_task()
        what = task.title if task else self.focus_project()
        title = f"Focus: {what}" if what else "Focus"
        self._events.add(Event(started.date(), TimeRange(first, last), title, "Quire focus block", self.BLOCK_COLOR))
        self._bus.publish(Topic.EVENTS)

    def toggle(self):
        now = self._clock.now()
        (self._timer.pause if self._timer.running else self._timer.start)(now)

    def reset(self):
        self._log_cut_short()
        self._end_block()
        self._timer.reset()

    def skip(self):
        self._log_cut_short()
        self._timer.skip(self._clock.now())

    def stop(self):
        """Quire is quitting: the timer can't carry on, so the focus so far counts."""
        self._log_cut_short()
        self._end_block()
        self._timer.reset()

    def _log_cut_short(self):
        """A focus session ended early still counts towards your focus time."""
        self.tick()  # a phase that has already run out counts as finished, not cut short
        session = self._timer.cut_short(self._clock.now())
        if session is not None:
            self._log_session(session.started, session.minutes, complete=False)

    def tick(self) -> FocusEvent | None:
        """Advance the timer; returns the phase that just ended, if any.

        After a long sleep several phases may have passed; they're all processed
        and the latest one is reported.
        """
        last = None
        block_started = self._timer.block_started
        while (event := self._timer.tick(self._clock.now())) is not None:
            last = FocusEvent(event.phase, event.next_phase, event.block_done)
            if event.phase is Phase.WORK:
                self._log_session(event.started, event.minutes, complete=True)
            if event.block_done and block_started is not None:
                self._add_block_event(block_started, event.started + timedelta(minutes=event.minutes))
                block_started = None
        return last

    def _log_session(self, started: datetime, minutes: int, complete: bool):
        task = self._focus_task()
        self._log.add(FocusSession(started, minutes, task.id if task else None,
                                   task.title if task else self.focus_project(), complete))
        self._bus.publish(Topic.FOCUS)

    # ---- stats ------------------------------------------------------------------

    def stats(self) -> FocusStats:
        today = self._clock.today()
        monday = today - timedelta(days=today.weekday())
        week = self._log.between(monday, monday + timedelta(days=6))
        todays = [s for s in week if s.started.date() == today]
        projects: dict[str, int] = {}
        for s in todays:
            if s.label:
                projects[s.label] = projects.get(s.label, 0) + s.minutes
        # Sessions cut short add their minutes, but only finished ones count as pomodori.
        return FocusStats(sum(s.complete for s in todays), sum(s.minutes for s in todays),
                          sum(s.complete for s in week), sum(s.minutes for s in week),
                          tuple(sorted(projects.items(), key=lambda p: (-p[1], p[0]))))
