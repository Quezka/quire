from __future__ import annotations

from datetime import date, timedelta

from ...domain import SleepLog, bedtime_for, sleep_stats
from ...domain.sleep import DEFAULT_GOAL_HOURS, DEFAULT_WAKE
from ..bus import ChangeBus, Topic
from ..inputs import SleepInput
from ..ports import Clock, KeyValueStore, SleepRepository
from ..records import SleepOverview, SleepRecord, sleep_record

NIGHTS = 14


class SleepService:
    """Use cases for the sleep log and the sleep goal."""

    PREFIX = "sleep."

    def __init__(self, logs: SleepRepository, settings: KeyValueStore, clock: Clock, bus: ChangeBus):
        self._logs = logs
        self._settings = settings
        self._clock = clock
        self._bus = bus

    def goal(self) -> tuple[float, int]:
        """(hours of sleep wanted, minute of the day to wake up)."""
        hours = self._settings.get(self.PREFIX + "hours")
        wake = self._settings.get(self.PREFIX + "wake")
        try:
            hours = float(hours) if hours else DEFAULT_GOAL_HOURS
            wake = int(wake) if wake else DEFAULT_WAKE
        except ValueError:
            hours, wake = DEFAULT_GOAL_HOURS, DEFAULT_WAKE
        return min(14.0, max(3.0, hours)), wake % (24 * 60)

    def save_goal(self, hours: float, wake: int):
        self._settings.set(self.PREFIX + "hours", str(min(14.0, max(3.0, hours))))
        self._settings.set(self.PREFIX + "wake", str(wake % (24 * 60)))
        self._bus.publish(Topic.SLEEP)

    def night(self, day: date) -> SleepRecord | None:
        log = self._logs.get(day)
        return sleep_record(log) if log else None

    def save(self, data: SleepInput) -> None:
        log = SleepLog(data.day, data.asleep, data.woke, data.quality, data.note.strip())
        log.validate()
        self._logs.put(log)
        self._bus.publish(Topic.SLEEP)

    def delete(self, day: date) -> None:
        self._logs.delete(day)
        self._bus.publish(Topic.SLEEP)

    def overview(self, nights: int = NIGHTS) -> SleepOverview:
        today = self._clock.today()
        logs = self._logs.between(today - timedelta(days=nights - 1), today)
        hours, wake = self.goal()
        stats = sleep_stats(logs, hours)
        return SleepOverview(hours, wake, bedtime_for(wake, hours),
                             tuple(sleep_record(log) for log in logs), stats.average_minutes,
                             stats.average_bedtime, stats.average_wake, stats.average_quality,
                             stats.enough, stats.shortfall_minutes)
