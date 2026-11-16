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
    idea_back: str = ""  # an older open idea, now and then, so it isn't lost
    routines: tuple[tuple[int, str], ...] = ()  # folded into one line <- were filling the slots, events dropped
    all_day: tuple[str, ...] = ()
    more: int = 0  # timed items past MAX_ITEMS


class DigestService:
    """Once in the morning and once in the evening, a short summary as a desktop notification (the phone has its own).
    Each is shown once a day, on whichever device-copy of Quire is running at that time."""

    PREFIX = "digest."
    MORNING, EVENING = 7 * 60 + 30, 21 * 60 + 30
    MAX_ITEMS = 12  # classes, events, shifts: all of a normal day
    SWITCH_HOUR = 15  # by-hand digest: today's before, tomorrow's after (same as the phone)

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
                return self.build(morning, today, mark=True)
        return None

    def current(self) -> Digest:
        """The digest for right now, asked for by hand: today's until 15:00, then tomorrow's. Doesn't mark it shown."""
        now: datetime = self._clock.now()
        return self.build(now.hour < self.SWITCH_HOUR, now.date(), mark=False)

    def build(self, morning: bool, today: date, mark: bool = False) -> Digest:
        day = today if morning else today + timedelta(days=1)
        agenda = self._planner.day_agenda(day)
        from ..dto import ItemKind
        timed = sorted((i.time.start, i.title) for i in agenda.items
                       if i.kind is not ItemKind.ROUTINE and not i.is_all_day)
        routines = tuple(sorted((i.time.start, i.title) for i in agenda.items if i.kind is ItemKind.ROUTINE))
        all_day = tuple(i.title for i in agenda.items if i.is_all_day and i.kind is not ItemKind.ROUTINE)
        items = tuple(timed[:self.MAX_ITEMS])
        due = tuple(t.task.title for t in agenda.tasks if not t.task.done)[:5]
        overdue = sum(1 for g in self._tasks.groups() for t in g.items if t.overdue)
        since = today - timedelta(days=1) if morning else today
        ideas = tuple(i.text for i in self._ideas.caught_between(since, today) if not i.done)[:5]
        back = self._ideas.resurfaced(mark=mark)
        return Digest(morning, items, due, overdue, ideas, back.text.splitlines()[0] if back else "",
                      routines, all_day, max(0, len(timed) - self.MAX_ITEMS))
