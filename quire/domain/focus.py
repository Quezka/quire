"""Pomodoro focus timer: the rules, independent of any clock or UI.

Time is always passed in, so the timer is exact (it measures against the
wall clock rather than counting ticks) and trivially testable.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .errors import ValidationError


class Phase(Enum):
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


@dataclass(frozen=True)
class FocusSettings:
    work_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    rounds: int = 4  # focus sessions before a long break
    auto_continue: bool = True  # start the next phase by itself

    def validate(self):
        for name, value, top in (("Focus", self.work_minutes, 180),
                                 ("Short break", self.short_break_minutes, 60),
                                 ("Long break", self.long_break_minutes, 120)):
            if not 1 <= value <= top:
                raise ValidationError(f"{name} must last between 1 and {top} minutes.")
        if not 1 <= self.rounds <= 12:
            raise ValidationError("Use between 1 and 12 rounds before a long break.")

    def minutes(self, phase: Phase) -> int:
        return {Phase.WORK: self.work_minutes, Phase.SHORT_BREAK: self.short_break_minutes,
                Phase.LONG_BREAK: self.long_break_minutes}[phase]


@dataclass(frozen=True)
class PhaseEnded:
    """Reported by `tick` when a phase runs out."""

    phase: Phase
    started: datetime
    minutes: int
    next_phase: Phase


class PomodoroTimer:
    def __init__(self, settings: FocusSettings | None = None):
        self.settings = settings or FocusSettings()
        self.phase = Phase.WORK
        self.completed = 0  # focus sessions finished in the current cycle
        self._remaining = timedelta(minutes=self.settings.work_minutes)
        self._ends_at: datetime | None = None  # set while running
        self._started_at: datetime | None = None  # when the current phase first started

    # ---- state ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._ends_at is not None

    @property
    def started(self) -> bool:
        """Whether the current phase has begun (it may be paused now)."""
        return self._started_at is not None

    @property
    def duration(self) -> timedelta:
        return timedelta(minutes=self.settings.minutes(self.phase))

    def remaining(self, now: datetime) -> timedelta:
        if self._ends_at is None:
            return self._remaining
        return max(self._ends_at - now, timedelta(0))

    def progress(self, now: datetime) -> float:
        """0.0 at the start of the phase, 1.0 when it's over."""
        total = self.duration.total_seconds()
        return 1 - self.remaining(now).total_seconds() / total if total else 1.0

    @property
    def round(self) -> int:
        """Which focus session of the cycle this is (1-based)."""
        return min(self.completed + (1 if self.phase is Phase.WORK else 0), self.settings.rounds)

    # ---- controls -----------------------------------------------------------------

    def start(self, now: datetime):
        if self.running:
            return
        if self._started_at is None:
            self._started_at = now
        self._ends_at = now + self._remaining

    def pause(self, now: datetime):
        if self.running:
            self._remaining = self.remaining(now)
            self._ends_at = None

    def reset(self):
        """Back to a fresh focus session; the cycle starts over."""
        self.phase = Phase.WORK
        self.completed = 0
        self._enter(self.phase, running_from=None)

    def skip(self, now: datetime):
        """Jump to the next phase without counting the current one as done."""
        self._enter(self._next_phase(counting=False), running_from=now if self.running else None)

    def apply_settings(self, settings: FocusSettings):
        """New durations take effect from the next phase, or now if nothing started yet."""
        settings.validate()
        self.settings = settings
        if self._started_at is None:
            self._remaining = self.duration

    def tick(self, now: datetime) -> PhaseEnded | None:
        """Advance if the running phase has run out; report what ended."""
        if not self.running or now < self._ends_at:
            return None
        ended_at = self._ends_at
        event = PhaseEnded(self.phase, self._started_at or ended_at - self.duration,
                           self.settings.minutes(self.phase),
                           self._next_phase(counting=True, dry_run=True))
        next_phase = self._next_phase(counting=True)
        self._enter(next_phase, running_from=ended_at if self.settings.auto_continue else None)
        return event

    # ---- internals ----------------------------------------------------------------

    def _next_phase(self, counting: bool, dry_run: bool = False) -> Phase:
        if self.phase is not Phase.WORK:
            if not dry_run and self.phase is Phase.LONG_BREAK:
                self.completed = 0
            return Phase.WORK
        done = self.completed + (1 if counting else 0)
        if not dry_run:
            self.completed = done
        return Phase.LONG_BREAK if done >= self.settings.rounds else Phase.SHORT_BREAK

    def _enter(self, phase: Phase, running_from: datetime | None):
        self.phase = phase
        self._remaining = self.duration
        self._started_at = running_from
        self._ends_at = running_from + self._remaining if running_from else None


@dataclass(frozen=True)
class FocusSession:
    """A completed focus session, for the stats."""

    started: datetime
    minutes: int
    task_id: int | None = None
    label: str = ""  # what it was spent on: the task's title or an ad-hoc project
