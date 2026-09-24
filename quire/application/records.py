"""Response models: what use cases hand to the outside, instead of domain entities.

Read-only snapshots with the same field names the entities have, so callers can
read them naturally but can't mutate domain state or depend on domain types.
The `*_record` functions map entities to records; only use cases call them.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..domain import (
    Course, Event, Grade, Job, Lesson, Note, Shift, ShiftPattern, Subject, Task, TaskKind,
    TimeRange,
)
from ..domain.focus import FocusSettings, Phase


@dataclass(frozen=True)
class TimeSpan:
    start: int  # minutes after midnight
    end: int

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class SlotRecord:
    weekday: int
    time: TimeSpan
    room: str = ""


@dataclass(frozen=True)
class CourseRecord:
    id: int
    name: str
    teacher: str
    room: str
    color: str
    slots: tuple[SlotRecord, ...]
    external_id: str | None  # the register subject it's linked to, if any


@dataclass(frozen=True)
class EventRecord:
    id: int
    day: date
    time: TimeSpan
    title: str
    details: str
    color: str


@dataclass(frozen=True)
class TaskRecord:
    id: int
    title: str
    kind: TaskKind
    course_id: int | None
    due: date | None
    done: bool
    details: str
    imported: bool  # came from the school register

    def is_overdue(self, today: date) -> bool:
        return not self.done and self.due is not None and self.due < today


@dataclass(frozen=True)
class NoteRecord:
    id: int
    title: str
    body: str
    course_id: int | None
    pinned: bool
    topic: str
    updated: datetime | None


@dataclass(frozen=True)
class PatternRecord:
    """One weekly shift of a job's schedule."""

    weekday: int
    start: int
    duration: int
    break_minutes: int
    since: date | None
    until: date | None

    @property
    def end(self) -> int:
        return self.start + self.duration


@dataclass(frozen=True)
class JobRecord:
    id: int
    name: str
    color: str
    hourly_rate: float | None
    deductions: float
    weekly: tuple[PatternRecord, ...]  # the schedule that applies from today on


@dataclass(frozen=True)
class ShiftRecord:
    id: int | None  # None for occurrences of a weekly schedule
    job_id: int
    day: date
    start: int
    duration: int
    break_minutes: int
    notes: str
    recurring: bool

    @property
    def end(self) -> int:
        return self.start + self.duration

    @property
    def ends_next_day(self) -> bool:
        return self.end > 24 * 60

    @property
    def paid_minutes(self) -> int:
        return self.duration - self.break_minutes


@dataclass(frozen=True)
class GradeRecord:
    external_id: str
    subject: str
    day: date
    display: str
    value: float | None
    component: str
    period: str
    notes: str
    cancelled: bool
    course_id: int | None

    @property
    def counts(self) -> bool:
        return self.value is not None and not self.cancelled


@dataclass(frozen=True)
class LessonRecord:
    day: date
    subject: str
    topic: str
    teacher: str
    hour: int
    course_id: int | None


@dataclass(frozen=True)
class SubjectRecord:
    external_id: str
    name: str
    teachers: tuple[str, ...]


@dataclass(frozen=True)
class FocusSettingsData:
    """Timer lengths; used both to show the settings and to change them."""

    work_minutes: int = 25
    short_break_minutes: int = 5
    long_break_minutes: int = 15
    rounds: int = 4
    auto_continue: bool = True


@dataclass(frozen=True)
class FocusState:
    phase: Phase
    remaining_seconds: float
    progress: float  # 0..1 through the current phase
    running: bool
    started: bool  # the phase has begun (it may be paused)
    round: int
    rounds: int
    completed: int  # focus sessions finished in this cycle


@dataclass(frozen=True)
class FocusEvent:
    """A phase just ended."""

    phase: Phase
    next_phase: Phase


# ---- mapping (used by the use cases) ------------------------------------------------

def span(time: TimeRange) -> TimeSpan:
    return TimeSpan(time.start, time.end)


def course_record(c: Course) -> CourseRecord:
    return CourseRecord(c.id, c.name, c.teacher, c.room, c.color,
                        tuple(SlotRecord(s.weekday, span(s.time), s.room) for s in c.slots),
                        c.external_id)


def event_record(e: Event) -> EventRecord:
    return EventRecord(e.id, e.day, span(e.time), e.title, e.details, e.color)


def task_record(t: Task) -> TaskRecord:
    return TaskRecord(t.id, t.title, t.kind, t.course_id, t.due, t.done, t.details,
                      t.external_id is not None)


def note_record(n: Note) -> NoteRecord:
    return NoteRecord(n.id, n.title, n.body, n.course_id, n.pinned, n.topic, n.updated)


def pattern_record(p: ShiftPattern) -> PatternRecord:
    return PatternRecord(p.weekday, p.start, p.duration, p.break_minutes, p.since, p.until)


def job_record(j: Job, today: date) -> JobRecord:
    return JobRecord(j.id, j.name, j.color, j.hourly_rate, j.deductions,
                     tuple(pattern_record(p) for p in j.active_schedule(today)))


def shift_record(s: Shift) -> ShiftRecord:
    return ShiftRecord(s.id, s.job_id, s.day, s.start, s.duration, s.break_minutes, s.notes,
                       s.recurring)


def grade_record(g: Grade) -> GradeRecord:
    return GradeRecord(g.external_id, g.subject, g.day, g.display, g.value, g.component,
                       g.period, g.notes, g.cancelled, g.course_id)


def lesson_record(l: Lesson) -> LessonRecord:
    return LessonRecord(l.day, l.subject, l.topic, l.teacher, l.hour, l.course_id)


def subject_record(s: Subject) -> SubjectRecord:
    return SubjectRecord(s.external_id, s.name, s.teachers)


def focus_settings_data(s: FocusSettings) -> FocusSettingsData:
    return FocusSettingsData(s.work_minutes, s.short_break_minutes, s.long_break_minutes,
                             s.rounds, s.auto_continue)
