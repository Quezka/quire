from __future__ import annotations

from datetime import date, datetime, timedelta

from ...domain import SleepLog, ValidationError, bedtime_for, regularity, should_wind_down, sleep_stats
from ...domain.sleep import DEFAULT_GOAL_HOURS, DEFAULT_WAKE, ENOUGH_RATIO
from ..bus import ChangeBus, Topic
from ..inputs import SleepInput
from ..ports import Clock, FocusLogRepository, KeyValueStore, SleepRepository
from ..records import SleepOverview, SleepRecord, sleep_record

NIGHTS = 14


class SleepService:
    """Use cases for the sleep log and the sleep goal."""

    PREFIX = "sleep."

    MIN_PER_GROUP = 3  # nights needed on each side before comparing focus

    def __init__(self, logs: SleepRepository, settings: KeyValueStore, clock: Clock, bus: ChangeBus,
                 focus: FocusLogRepository | None = None):
        self._focus = focus
        self._reminded_on: date | None = None
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

    # ---- one-tap logging: "going to sleep" now, "awake" later ----

    def asleep_since(self) -> datetime | None:
        value = self._settings.get(self.PREFIX + "pending")
        try:
            return datetime.fromisoformat(value) if value else None
        except ValueError:
            return None

    def go_to_sleep(self) -> None:
        self._settings.set(self.PREFIX + "pending", self._clock.now().isoformat(timespec="minutes"))
        self._bus.publish(Topic.SLEEP)

    def cancel_going_to_sleep(self) -> None:
        self._settings.set(self.PREFIX + "pending", None)
        self._bus.publish(Topic.SLEEP)

    def wake_up(self) -> SleepRecord:
        """Close the night you started with `go_to_sleep`, waking now."""
        since = self.asleep_since()
        if since is None:
            raise ValidationError("Say when you go to sleep first.")
        now = self._clock.now()
        if not timedelta(minutes=30) <= now - since <= timedelta(hours=18):
            raise ValidationError("A night's sleep is between 30 minutes and 18 hours.")  # a forgotten start
        log = SleepLog(now.date(), since.hour * 60 + since.minute, now.hour * 60 + now.minute)
        log.validate()
        self._logs.put(log)
        self._settings.set(self.PREFIX + "pending", None)
        self._bus.publish(Topic.SLEEP)
        return sleep_record(log)

    # ---- bedtime reminder ----

    def remind_enabled(self) -> bool:
        return self._settings.get(self.PREFIX + "remind") != "0"

    def set_remind(self, on: bool) -> None:
        self._settings.set(self.PREFIX + "remind", "1" if on else "0")
        self._bus.publish(Topic.SLEEP)

    def reminder(self) -> int | None:
        """Bedtime (minute of day) when it's time to wind down, once a day; else None."""
        if not self.remind_enabled() or self.asleep_since() is not None:
            return None
        now = self._clock.now()
        hours, wake = self.goal()
        bedtime = bedtime_for(wake, hours)
        if self._reminded_on == now.date() or not should_wind_down(now.hour * 60 + now.minute, bedtime):
            return None
        self._reminded_on = now.date()
        return bedtime

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

    def _focus_after(self, today: date, hours: float) -> tuple[int | None, int | None]:
        """Average focus minutes on days after a night that reached the goal, and after one that
        didn't, over the last 30 days; None until each side has a few nights to go on."""
        if self._focus is None:
            return None, None
        first = today - timedelta(days=29)
        logs = self._logs.between(first, today)
        per_day: dict[date, int] = {}
        for session in self._focus.between(first, today):
            per_day[session.started.date()] = per_day.get(session.started.date(), 0) + session.minutes
        if not per_day:
            return None, None  # no focus sessions logged at all: nothing to compare
        goal = round(hours * 60) * ENOUGH_RATIO
        enough = [per_day.get(log.day, 0) for log in logs if log.minutes >= goal]
        short = [per_day.get(log.day, 0) for log in logs if log.minutes < goal]
        if len(enough) < self.MIN_PER_GROUP or len(short) < self.MIN_PER_GROUP:
            return None, None
        return round(sum(enough) / len(enough)), round(sum(short) / len(short))

    def overview(self, nights: int = NIGHTS) -> SleepOverview:
        today = self._clock.today()
        logs = self._logs.between(today - timedelta(days=nights - 1), today)
        hours, wake = self.goal()
        stats = sleep_stats(logs, hours)
        recent = [log for log in logs if log.day > today - timedelta(days=7)]
        before = [log for log in logs if log.day <= today - timedelta(days=7)]
        last_week = sleep_stats(before, hours).average_minutes if len(before) >= 3 and len(recent) >= 3 else None
        after_enough, after_short = self._focus_after(today, hours)
        since = self.asleep_since()
        return SleepOverview(hours, wake, bedtime_for(wake, hours),
                             tuple(sleep_record(log) for log in logs), stats.average_minutes,
                             stats.average_bedtime, stats.average_wake, stats.average_quality,
                             stats.enough, stats.shortfall_minutes, stats.bedtime_spread,
                             regularity(stats.bedtime_spread) if stats.nights >= 3 else "",
                             stats.streak, last_week, after_enough, after_short,
                             since.hour * 60 + since.minute if since else None)
