"""Read models the use cases hand to the presentation layer.

Built from records (see records.py), never from domain entities.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from .records import CourseRecord, JobRecord, NotebookRecord, ShiftRecord, TaskRecord, TimeSpan
from .types import DueBucket


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
    time: TimeSpan
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
    task: TaskRecord
    course: CourseRecord | None
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
    course: CourseRecord | None
    topic: str = ""
    snippet: str = ""  # the start of the text after the title
    notebook: NotebookRecord | None = None


@dataclass(frozen=True)
class NoteGroup:
    """Notes sharing a class (or notebook) and topic, for the grouped notes list."""

    course: CourseRecord | None
    topic: str  # "" for notes without a topic
    notes: tuple[NoteSummary, ...]
    notebook: NotebookRecord | None = None


@dataclass(frozen=True)
class ShiftItem:
    shift: ShiftRecord
    job: JobRecord | None
    pay: float | None  # gross; None if the job has no rate
    net: float | None  # after the job's tax and deductions


@dataclass(frozen=True)
class JobTotal:
    job: JobRecord | None
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


@dataclass(frozen=True)
class ShiftPreview:
    """What a shift being edited adds up to, before it's saved."""

    duration: int
    paid_minutes: int
    ends_next_day: bool
    pay: float | None
    net: float | None
