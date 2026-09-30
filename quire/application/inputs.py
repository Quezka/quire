"""Request models: what callers hand to use cases to create or change things.

Only the fields a user can edit. The use case loads the stored entity and applies
these, so fields the caller doesn't know about (sync ids, history) survive.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from ..domain import TaskKind


@dataclass(frozen=True)
class SlotInput:
    weekday: int
    start: int
    end: int
    room: str = ""


@dataclass(frozen=True)
class CourseInput:
    name: str
    teacher: str = ""
    room: str = ""
    color: str = "#4f7cff"
    slots: tuple[SlotInput, ...] = ()


@dataclass(frozen=True)
class EventInput:
    day: date
    start: int
    end: int
    title: str
    details: str = ""
    color: str = "#8a8f98"


@dataclass(frozen=True)
class TaskInput:
    title: str
    kind: TaskKind = TaskKind.TASK
    course_id: int | None = None
    due: date | None = None
    details: str = ""
    done: bool = False


@dataclass(frozen=True)
class NoteInput:
    body: str
    course_id: int | None = None
    pinned: bool = False
    topic: str = ""
    notebook_id: int | None = None  # instead of a class: one or the other


@dataclass(frozen=True)
class NotebookInput:
    name: str
    color: str = "#8a8f98"


@dataclass(frozen=True)
class JobInput:
    name: str
    color: str = "#0090ff"
    hourly_rate: float | None = None
    deductions: float = 0.0


@dataclass(frozen=True)
class PatternInput:
    """One weekly shift; `end` at or before `start` means it ends the next day."""

    weekday: int
    start: int
    end: int
    break_minutes: int = 0


@dataclass(frozen=True)
class ShiftInput:
    job_id: int
    day: date
    start: int
    end: int  # at or before `start` means the next day
    break_minutes: int = 0
    notes: str = ""
