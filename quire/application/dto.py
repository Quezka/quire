"""Read models the use cases hand to the presentation layer."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from ..domain import Course, DueBucket, Task, TimeRange


class ItemKind(Enum):
    CLASS = "class"
    EVENT = "event"


@dataclass(frozen=True)
class AgendaItem:
    kind: ItemKind
    ref_id: int  # course id for classes, event id for events
    day: date
    time: TimeRange
    title: str
    color: str
    room: str = ""
    teacher: str = ""
    details: str = ""


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
