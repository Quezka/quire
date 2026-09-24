from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from ..dto import AgendaItem, ItemKind
from ..ports import Clock, KeyValueStore
from .planner import PlannerService

# How long after something starts a reminder still makes sense (the app was busy, the
# laptop just woke up). Anything older is skipped, not announced late.
GRACE = timedelta(minutes=2)


@dataclass(frozen=True)
class ReminderSettings:
    minutes_before: int | None = 10  # None: no reminders
    events: bool = True
    classes: bool = False
    shifts: bool = True


@dataclass(frozen=True)
class Reminder:
    item: AgendaItem  # the whole item: for a shift past midnight, its first part
    starts: datetime
    minutes_left: int  # 0 when it's starting now


class ReminderService:
    """Use cases for "remind me before my next thing starts".

    The UI calls `due()` every so often and shows what it returns; each start is
    announced once per run of the app.
    """

    PREFIX = "reminders."
    CHOICES = (None, 0, 5, 10, 15, 30, 60)  # minutes before

    def __init__(self, planner: PlannerService, settings: KeyValueStore, clock: Clock):
        self._planner = planner
        self._settings = settings
        self._clock = clock
        self._sent: set[tuple] = set()

    def settings(self) -> ReminderSettings:
        defaults = ReminderSettings()
        minutes = self._settings.get(self.PREFIX + "minutes")
        if minutes is None:
            before = defaults.minutes_before
        else:
            before = int(minutes) if minutes.isdigit() else None

        def flag(name: str, default: bool) -> bool:
            value = self._settings.get(self.PREFIX + name)
            return default if value is None else value == "1"

        return ReminderSettings(before, flag("events", defaults.events),
                                flag("classes", defaults.classes), flag("shifts", defaults.shifts))

    def save_settings(self, settings: ReminderSettings):
        before = settings.minutes_before
        self._settings.set(self.PREFIX + "minutes", "off" if before is None else str(before))
        for name in ("events", "classes", "shifts"):
            self._settings.set(self.PREFIX + name, "1" if getattr(settings, name) else "0")

    def _wanted(self, kind: ItemKind, settings: ReminderSettings) -> bool:
        if kind is ItemKind.CLASS:
            return settings.classes
        if kind is ItemKind.EVENT:
            return settings.events
        return settings.shifts

    def due(self) -> list[Reminder]:
        """Things starting within the reminder time that haven't been announced yet."""
        settings = self.settings()
        if settings.minutes_before is None:
            return []
        now = self._clock.now()
        horizon = now + timedelta(minutes=settings.minutes_before)
        earliest = now - GRACE
        found = []
        for item in self._planner.items_between(earliest.date(), horizon.date()):
            if not self._wanted(item.kind, settings):
                continue
            day, minute = item.origin or (item.day, item.time.start)
            if (day, minute) != (item.day, item.time.start):
                continue  # the after-midnight part of something that started yesterday
            starts = datetime.combine(day, time()) + timedelta(minutes=minute)
            key = (item.kind, item.ref_id, starts)
            if earliest < starts <= horizon and key not in self._sent:
                self._sent.add(key)
                left = max(0, -(-int((starts - now).total_seconds()) // 60))  # rounded up
                found.append(Reminder(item, starts, left))
        return sorted(found, key=lambda r: r.starts)
