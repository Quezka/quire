"""Core entities and business rules.

Pure Python: nothing here knows about Qt, SQLite or any other framework.
Times of day are minutes after midnight; weekdays follow Python's
convention (0 = Monday ... 6 = Sunday).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum

from .errors import ValidationError

MINUTES_PER_DAY = 24 * 60
UPCOMING_DAYS = 7


@dataclass(frozen=True)
class TimeRange:
    start: int
    end: int

    def __post_init__(self):
        if not (0 <= self.start < MINUTES_PER_DAY and 0 < self.end <= MINUTES_PER_DAY):
            raise ValidationError("Times must fall within a single day.")
        if self.end <= self.start:
            raise ValidationError("The end time must be after the start time.")

    @property
    def duration(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class ClassSlot:
    """One weekly meeting of a course."""

    weekday: int
    time: TimeRange
    room: str = ""

    def __post_init__(self):
        if not 0 <= self.weekday <= 6:
            raise ValidationError("Weekday must be between Monday and Sunday.")


@dataclass
class Course:
    name: str
    teacher: str = ""
    room: str = ""
    color: str = "#4f7cff"
    slots: list[ClassSlot] = field(default_factory=list)
    id: int | None = None

    def validate(self):
        if not self.name.strip():
            raise ValidationError("Give the course a name.")

    def slots_on(self, weekday: int) -> list[ClassSlot]:
        return sorted((s for s in self.slots if s.weekday == weekday), key=lambda s: s.time.start)

    def room_for(self, slot: ClassSlot) -> str:
        return slot.room or self.room

    def next_meeting_after(self, day: date) -> date | None:
        weekdays = {s.weekday for s in self.slots}
        for offset in range(1, 8):
            candidate = day + timedelta(days=offset)
            if candidate.weekday() in weekdays:
                return candidate
        return None


@dataclass
class Event:
    """A one-off entry in the day planner."""

    day: date
    time: TimeRange
    title: str
    details: str = ""
    color: str = "#8a8f98"
    id: int | None = None

    def validate(self):
        if not self.title.strip():
            raise ValidationError("Give the event a title.")


class TaskKind(str, Enum):
    TASK = "task"
    HOMEWORK = "homework"
    ASSIGNMENT = "assignment"
    EXAM = "exam"
    READING = "reading"


class DueBucket(Enum):
    """When a task is due, relative to today. Declaration order is display order."""

    OVERDUE = "overdue"
    TODAY = "today"
    UPCOMING = "upcoming"
    LATER = "later"
    UNDATED = "undated"
    DONE = "done"


@dataclass
class Task:
    title: str
    kind: TaskKind = TaskKind.TASK
    course_id: int | None = None
    due: date | None = None
    done: bool = False
    details: str = ""
    id: int | None = None

    def validate(self):
        if not self.title.strip():
            raise ValidationError("Give the task a title.")

    def is_overdue(self, today: date) -> bool:
        return not self.done and self.due is not None and self.due < today

    def bucket(self, today: date) -> DueBucket:
        if self.done:
            return DueBucket.DONE
        if self.due is None:
            return DueBucket.UNDATED
        if self.due < today:
            return DueBucket.OVERDUE
        if self.due == today:
            return DueBucket.TODAY
        if (self.due - today).days <= UPCOMING_DAYS:
            return DueBucket.UPCOMING
        return DueBucket.LATER


def derive_note_title(body: str) -> str:
    """A note's title is its first non-empty line, minus markdown heading marks."""
    for line in body.splitlines():
        text = line.strip().lstrip("#").strip()
        if text:
            return text[:120]
    return "Untitled"


@dataclass
class Note:
    body: str = ""
    course_id: int | None = None
    pinned: bool = False
    updated: datetime | None = None
    id: int | None = None

    @property
    def title(self) -> str:
        return derive_note_title(self.body)
