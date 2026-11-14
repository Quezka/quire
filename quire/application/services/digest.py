from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..ports import Clock, KeyValueStore


@dataclass(frozen=True)
class Digest:
    """The morning digest (today) or the evening one (tomorrow, and today's ideas)."""

    morning: bool
    items: tuple[tuple[int, str], ...]  # (start minute, title) of the day it's about
    due: tuple[str, ...]  # tasks due that day
    overdue: int
    ideas: tuple[str, ...]  # caught today (evening) or since yesterday (morning), still open


class DigestService:
    """Once in the morning and once in the evening, a short summary as a desktop notification (the phone has its own).
    Each is shown once a day, on whichever device-copy of Quire is running at that time."""

    PREFIX = "digest."
    MORNING, EVENING = 7 * 60 + 30, 21 * 60 + 30

    def __init__(self, planner, tasks, ideas, settings: KeyValueStore, clock: Clock):
        self._planner, self._tasks, self._ideas = planner, tasks, ideas
        self._settings, self._clock = settings, clock

    def enabled(self) -> bool:
        return self._settings.get(self.PREFIX + "on") != "0"

    def set_enabled(self, on: bool):
        self._settings.set(self.PREFIX + "on", "1" if on else "0")

    def due_now(self) -> Digest | None:
        """The digest to show now, if one is due and wasn't shown today; marks it shown."""
        if not self.enabled():
            return None
        now: datetime = self._clock.now()
        minute, today = now.hour * 60 + now.minute, now.date()
        for morning, at, key in ((False, self.EVENING, "evening"), (True, self.MORNING, "morning")):
            if minute >= at and self._settings.get(self.PREFIX + key) != today.isoformat():
                if morning and minute >= self.EVENING:
                    continue  # too late for the morning one
                self._settings.set(self.PREFIX + key, today.isoformat())
                return self.build(morning, today)
        return None

    def build(self, morning: bool, today: date) -> Digest:
        day = today if morning else today + timedelta(days=1)
        agenda = self._planner.day_agenda(day)
        items = tuple(sorted((i.time.start, i.title) for i in agenda.items))[:6]
        due = tuple(t.task.title for t in agenda.tasks if not t.task.done)[:5]
        overdue = sum(1 for g in self._tasks.groups() for t in g.items if t.overdue)
        since = today - timedelta(days=1) if morning else today
        ideas = tuple(i.text for i in self._ideas.caught_between(since, today) if not i.done)[:5]
        return Digest(morning, items, due, overdue, ideas)
