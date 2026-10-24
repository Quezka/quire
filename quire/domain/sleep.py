"""Sleep log rules. Pure Python, like the rest of the domain.

A night is logged on the day you woke up: when you fell asleep and when you woke, as
minutes after midnight. Falling asleep later in the day than waking means the evening before.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .errors import ValidationError

MINUTES_PER_DAY = 24 * 60
MIN_SLEEP = 30  # shorter than this is a nap, not a night
MAX_SLEEP = 18 * 60
DEFAULT_GOAL_HOURS = 8.0
DEFAULT_WAKE = 6 * 60
ENOUGH_RATIO = 0.9  # a night counts as enough from 90% of the goal


@dataclass
class SleepLog:
    day: date  # the day you woke up
    asleep: int  # minutes after midnight
    woke: int
    quality: int | None = None  # 1 (awful) to 5 (great); None when not rated
    note: str = ""

    def validate(self):
        if not (0 <= self.asleep < MINUTES_PER_DAY and 0 <= self.woke < MINUTES_PER_DAY):
            raise ValidationError("Times must fall within a single day.")
        if self.quality is not None and not 1 <= self.quality <= 5:
            raise ValidationError("Rate the night from 1 to 5.")
        if not MIN_SLEEP <= self.minutes <= MAX_SLEEP:
            raise ValidationError("A night's sleep is between 30 minutes and 18 hours.")

    @property
    def minutes(self) -> int:
        return (self.woke - self.asleep) % MINUTES_PER_DAY

    @property
    def fell_asleep_on(self) -> date:
        """The calendar day the night began."""
        return self.day - timedelta(days=1) if self.asleep > self.woke else self.day


def bedtime_for(wake: int, hours: float) -> int:
    """When to be asleep to wake at `wake` after `hours` of sleep."""
    return (wake - round(hours * 60)) % MINUTES_PER_DAY


def _evening_minutes(minute: int) -> int:
    """Bedtimes either side of midnight average sensibly when measured from noon."""
    return (minute - 12 * 60) % MINUTES_PER_DAY


@dataclass(frozen=True)
class SleepStats:
    nights: int
    average_minutes: int
    average_bedtime: int | None
    average_wake: int | None
    average_quality: float | None
    enough: int  # nights that reached the goal
    shortfall_minutes: int  # total missing against the goal over the period


def sleep_stats(logs: list[SleepLog], goal_hours: float) -> SleepStats:
    if not logs:
        return SleepStats(0, 0, None, None, None, 0, 0)
    goal = round(goal_hours * 60)
    n = len(logs)
    bed = sum(_evening_minutes(log.asleep) for log in logs) // n
    wake = sum(log.woke for log in logs) // n
    rated = [log.quality for log in logs if log.quality]
    return SleepStats(
        n, sum(log.minutes for log in logs) // n,
        (bed + 12 * 60) % MINUTES_PER_DAY, wake,
        sum(rated) / len(rated) if rated else None,
        sum(log.minutes >= goal * ENOUGH_RATIO for log in logs),
        sum(max(0, goal - log.minutes) for log in logs))
