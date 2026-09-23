"""Read models the use cases hand to the presentation layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from ..domain import Course, DueBucket, Job, Shift, Task, TimeRange, net_pay


class ItemKind(Enum):
    CLASS = "class"
    EVENT = "event"
    SHIFT = "shift"  # a one-off shift; ref_id is the shift id
    WEEKLY_SHIFT = "weekly_shift"  # from a job's weekly schedule; ref_id is the job id


@dataclass(frozen=True)
class AgendaItem:
    kind: ItemKind
    ref_id: int  # course id for classes, event id for events, shift id for shifts
    day: date
    time: TimeRange
    title: str
    color: str
    room: str = ""
    teacher: str = ""
    details: str = ""
    # For items that aren't stored on their own (weekly shifts) or span midnight:
    # the day and minute the whole item starts.
    origin: tuple[date, int] | None = None


@dataclass(frozen=True)
class TaskItem:
    task: Task
    course: Course | None
    overdue: bool


@dataclass(frozen=True)
class DayAgenda:
    day: date
    is_today: bool
    items: tuple[AgendaItem, ...]
    tasks: tuple[TaskItem, ...]
    journal: str
    has_courses: bool

    @property
    def class_count(self) -> int:
        return sum(1 for i in self.items if i.kind is ItemKind.CLASS)

    @property
    def event_count(self) -> int:
        return sum(1 for i in self.items if i.kind is ItemKind.EVENT)

    @property
    def shift_count(self) -> int:
        return len({(i.kind, i.ref_id, i.origin) for i in self.items
                    if i.kind in (ItemKind.SHIFT, ItemKind.WEEKLY_SHIFT)})

    @property
    def open_task_count(self) -> int:
        return sum(1 for t in self.tasks if not t.task.done)


@dataclass(frozen=True)
class WeekAgenda:
    days: tuple[date, ...]
    items: tuple[AgendaItem, ...]
    today_index: int | None
    has_courses: bool

    @property
    def monday(self) -> date:
        return self.days[0]


@dataclass(frozen=True)
class TaskGroup:
    bucket: DueBucket
    items: tuple[TaskItem, ...]


@dataclass(frozen=True)
class NoteSummary:
    id: int
    title: str
    pinned: bool
    updated: datetime | None
    course: Course | None
    topic: str = ""


@dataclass(frozen=True)
class NoteGroup:
    """Notes sharing a course and topic, for the grouped notes list."""

    course: Course | None
    topic: str  # "" for notes without a topic
    notes: tuple[NoteSummary, ...]


@dataclass(frozen=True)
class ShiftItem:
    shift: Shift
    job: Job | None

    @property
    def pay(self) -> float | None:
        """Gross pay."""
        return self.shift.pay(self.job.hourly_rate if self.job else None)

    @property
    def net(self) -> float | None:
        return net_pay(self.pay, self.job.deductions if self.job else 0.0)


@dataclass(frozen=True)
class JobTotal:
    job: Job | None
    minutes: int
    pay: float | None  # gross
    net: float | None = None


@dataclass(frozen=True)
class WorkSummary:
    first: date
    last: date
    minutes: int  # paid minutes
    pay: float | None  # gross; None when no job has a rate
    shifts: int
    per_job: tuple[JobTotal, ...]
    net: float | None = None  # after each job's tax and deductions
