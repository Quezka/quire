from __future__ import annotations

from datetime import timedelta

from ...domain.ical import CalendarEntry, to_ics
from ..dto import AgendaItem, ItemKind
from ..ports import Clock, KeyValueStore, SystemCalendar

DAYS_BACK = 30
DAYS_AHEAD = 180


def _entry(item: AgendaItem) -> CalendarEntry:
    kind = item.kind.value
    ident = item.ref_id if item.ref_id is not None else item.title
    return CalendarEntry(f"{kind}-{ident}-{item.day.isoformat()}-{item.time.start}@quire", item.title, item.day,
                         item.time.start, item.time.end, item.is_all_day, item.details, item.room)


class CalendarService:
    """Showing Quire's agenda in the computer's own calendar: one way, from Quire to a calendar file
    the system reads. Nothing comes back; you keep editing in Quire."""

    ENABLED = "calendar.enabled"

    def __init__(self, planner, tasks, system: SystemCalendar, settings: KeyValueStore, clock: Clock):
        self._planner = planner
        self._tasks = tasks
        self._system = system
        self._settings = settings
        self._clock = clock

    def enabled(self) -> bool:
        return self._settings.get(self.ENABLED) == "1"

    def can_subscribe(self) -> bool:
        """Whether the system keeps following the file, rather than importing it once."""
        return self._system.can_subscribe()

    def set_enabled(self, on: bool) -> None:
        self._settings.set(self.ENABLED, "1" if on else "0")
        if on:
            self.publish()
            self._system.connect()
        else:
            self._system.disconnect()

    def _entries(self) -> list[CalendarEntry]:
        today = self._clock.today()
        items = self._planner.items_between(today - timedelta(days=DAYS_BACK), today + timedelta(days=DAYS_AHEAD))
        entries = [_entry(i) for i in items if not i.is_milestone and i.kind is not ItemKind.ROUTINE]
        for group in self._tasks.groups():
            for item in group.items:
                t = item.task
                if t.due is not None:
                    entries.append(CalendarEntry(f"task-{t.id}@quire", t.title, t.due, all_day=True, details=t.details))
        return entries

    def publish(self) -> None:
        """Write the calendar file, if this is switched on. Cheap when nothing changed."""
        if self.enabled():
            self._system.publish(to_ics(self._entries(), "Quire", self._clock.now()))

    def open(self) -> None:
        """Hand the file to the system's calendar app (on Windows that imports it)."""
        self._settings.set(self.ENABLED, "1")
        self.publish()
        self._system.open()
