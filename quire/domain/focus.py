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
    block_done: bool = False  # the focus block (see PomodoroTimer.start_block) is over with this phase


MAX_BLOCK_MINUTES = 12 * 60


def plan_block(total_minutes: int, settings: FocusSettings) -> list[tuple[Phase, int]]:
    """How a focus block of `total_minutes` splits into focus and breaks: the usual rounds, the last focus
    cut to fit, and never a break at the end (the block ends with focus)."""
    if not 1 <= total_minutes <= MAX_BLOCK_MINUTES:
        raise ValidationError(f"A focus block lasts between 1 minute and {MAX_BLOCK_MINUTES // 60} hours.")
    plan, left, done = [], total_minutes, 0
    while left > 0:
        work = min(settings.work_minutes, left)
        plan.append((Phase.WORK, work))
        left -= work
        done += 1
        rest = Phase.LONG_BREAK if done % settings.rounds == 0 else Phase.SHORT_BREAK
        if left <= settings.minutes(rest):
            # no room for a break and more focus after it: the last focus runs to the end instead
            plan[-1] = (Phase.WORK, work + left)
            break
        plan.append((rest, settings.minutes(rest)))
        left -= settings.minutes(rest)
    return plan


class PomodoroTimer:
    def __init__(self, settings: FocusSettings | None = None):
        self.settings = settings or FocusSettings()
        self.phase = Phase.WORK
        self.completed = 0  # focus sessions finished in the current cycle
        self._length = timedelta(minutes=self.settings.work_minutes)  # of the current phase
        self._remaining = self._length
        self._ends_at: datetime | None = None  # set while running
        self._started_at: datetime | None = None  # when the current phase first started
        self.block_started: datetime | None = None  # a focus block (start_block) is on
        self.block_ends: datetime | None = None

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
        """How long the current phase lasts (set when it began, even if settings change)."""
        return self._length

    def elapsed(self, now: datetime) -> timedelta:
        """Time spent in the current phase so far, not counting pauses."""
        return self._length - self.remaining(now) if self.started else timedelta(0)

    def cut_short(self, now: datetime) -> FocusSession | None:
        """The unfinished focus session that ending the phase now would leave, if any.

        Only focus phases count, and only a whole minute or more of them.
        """
        if self.phase is not Phase.WORK or not self.started:
            return None
        minutes = round(self.elapsed(now).total_seconds() / 60)
        if minutes < 1:
            return None
        return FocusSession(self._started_at, minutes, complete=False)

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
        """Back to a fresh focus session; the cycle starts over (and any focus block ends)."""
        self.phase = Phase.WORK
        self.completed = 0
        self.block_started = self.block_ends = None
        self._enter(self.phase, running_from=None)

    def start_block(self, now: datetime, total_minutes: int):
        """Focus for `total_minutes` in all, split into rounds and breaks (see plan_block): the phases run one
        after the other by themselves, the last focus is cut to fit, and the block stops at its end."""
        plan_block(total_minutes, self.settings)  # checks the length
        self.reset()
        self.block_started, self.block_ends = now, now + timedelta(minutes=total_minutes)
        self._enter(Phase.WORK, running_from=now)

    @property
    def in_block(self) -> bool:
        return self.block_ends is not None

    def skip(self, now: datetime):
        """Jump to the next phase without counting the current one as done."""
        self._enter(self._next_phase(counting=False), running_from=now if self.running else None)

    def apply_settings(self, settings: FocusSettings):
        """New durations take effect from the next phase, or now if nothing started yet."""
        settings.validate()
        self.settings = settings
        if self._started_at is None:
            self._length = self._remaining = timedelta(minutes=settings.minutes(self.phase))

    def tick(self, now: datetime) -> PhaseEnded | None:
        """Advance if the running phase has run out; report what ended."""
        if not self.running or now < self._ends_at:
            return None
        ended_at = self._ends_at
        started = self._started_at or ended_at - self.duration
        minutes = round(self.duration.total_seconds() / 60)
        ended_phase = self.phase
        next_phase = self._next_phase(counting=True)
        if self.block_ends is not None:
            left = self.block_ends - ended_at
            room = timedelta(minutes=self.settings.minutes(next_phase))
            if left <= timedelta(0):
                # the block is over
                self.block_started = self.block_ends = None
                self.phase, self.completed = Phase.WORK, 0
                self._enter(Phase.WORK, running_from=None)
                return PhaseEnded(ended_phase, started, minutes, Phase.WORK, block_done=True)
            if next_phase is not Phase.WORK and left <= room:
                next_phase = Phase.WORK  # no room for a break and focus after it: focus to the end (see plan_block)
            self._enter(next_phase, running_from=ended_at)  # a block always carries on by itself
        else:
            self._enter(next_phase, running_from=ended_at if self.settings.auto_continue else None)
        return PhaseEnded(ended_phase, started, minutes, next_phase)

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
        self._length = self._remaining = timedelta(minutes=self.settings.minutes(phase))
        if self.block_ends is not None and running_from is not None:
            # the last focus of a block is cut to fit
            self._length = self._remaining = max(timedelta(minutes=1), min(self._length, self.block_ends - running_from))
        self._started_at = running_from
        self._ends_at = running_from + self._remaining if running_from else None


@dataclass(frozen=True)
class FocusSession:
    """A focus session, for the stats.

    One cut short (skipped or reset) isn't `complete`: its minutes count towards your focus
    time, but it isn't counted as a pomodoro.
    """

    started: datetime
    minutes: int
    task_id: int | None = None
    label: str = ""  # what it was spent on: the task's title or an ad-hoc project
    complete: bool = True
