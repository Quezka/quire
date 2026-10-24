from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from ..dto import ItemKind
from ..ports import Clock, KeyValueStore, QuietSwitch
from .planner import PlannerService

CHECK_DAYS = 1  # look this many days past today for what is coming


@dataclass(frozen=True)
class QuietSettings:
    """Silence notifications while these things are on. Milestones and routines have no
    duration, so they never silence anything."""

    enabled: bool = False
    classes: bool = True
    events: bool = True
    shifts: bool = False


@dataclass(frozen=True)
class QuietStatus:
    active: bool
    until: datetime | None  # when the current quiet period ends
    next_start: datetime | None  # when the next one begins, if not quiet now


def merge_periods(periods: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Sorted, with overlapping or touching periods joined (a shift over midnight is one)."""
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(periods):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def status_at(periods: list[tuple[datetime, datetime]], now: datetime) -> QuietStatus:
    for start, end in merge_periods(periods):
        if start <= now < end:
            return QuietStatus(True, end, None)
    upcoming = [start for start, _end in merge_periods(periods) if start > now]
    return QuietStatus(False, None, min(upcoming) if upcoming else None)


class QuietService:
    """Turns the computer's Do Not Disturb on while a class, event or shift is on, and off
    again afterwards. Only undoes what it did itself."""

    PREFIX = "quiet."

    def __init__(self, planner: PlannerService, settings: KeyValueStore, clock: Clock,
                 switch: QuietSwitch):
        self._planner = planner
        self._settings = settings
        self._clock = clock
        self._switch = switch

    # ---- settings ----

    def settings(self) -> QuietSettings:
        d = QuietSettings()

        def flag(name: str, default: bool) -> bool:
            value = self._settings.get(self.PREFIX + name)
            return default if value is None else value == "1"

        return QuietSettings(flag("enabled", d.enabled), flag("classes", d.classes),
                             flag("events", d.events), flag("shifts", d.shifts))

    def save_settings(self, settings: QuietSettings):
        for name in ("enabled", "classes", "events", "shifts"):
            self._settings.set(self.PREFIX + name, "1" if getattr(settings, name) else "0")
        self.tick()

    def available(self) -> bool:
        return self._switch.available()

    def method(self) -> str:
        return self._switch.name

    # ---- what is quiet when ----

    def _wanted(self, kind: ItemKind, settings: QuietSettings) -> bool:
        if kind is ItemKind.CLASS:
            return settings.classes
        if kind is ItemKind.EVENT:
            return settings.events
        if kind in (ItemKind.SHIFT, ItemKind.WEEKLY_SHIFT):
            return settings.shifts
        return False

    def periods(self, now: datetime, settings: QuietSettings | None = None):
        settings = settings or self.settings()
        today = now.date()
        found = []
        for item in self._planner.items_between(today, today + timedelta(days=CHECK_DAYS)):
            if item.is_milestone or not self._wanted(item.kind, settings):
                continue
            midnight = datetime.combine(item.day, time())
            found.append((midnight + timedelta(minutes=item.time.start),
                          midnight + timedelta(minutes=item.time.end)))
        return merge_periods(found)

    def status(self) -> QuietStatus:
        settings = self.settings()
        if not settings.enabled:
            return QuietStatus(False, None, None)
        now = self._clock.now()
        return status_at(self.periods(now, settings), now)

    # ---- applying ----

    def tick(self) -> bool:
        """Bring the computer in line with the schedule; true while quiet."""
        want = self.status().active and self._switch.available()
        owned = self._settings.get(self.PREFIX + "applied") == "1"
        if want and not owned:
            self._switch.set_quiet(True)
            self._settings.set(self.PREFIX + "applied", "1")
        elif not want and owned:
            self._switch.set_quiet(False)
            self._settings.set(self.PREFIX + "applied", None)
        return want

    def release(self):
        """Give the notifications back (Quire is closing, or it crashed while quiet)."""
        if self._settings.get(self.PREFIX + "applied") == "1":
            self._switch.set_quiet(False)
            self._settings.set(self.PREFIX + "applied", None)
