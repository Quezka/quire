"""Interfaces the application needs from the outside world.

Infrastructure provides the implementations; the application only ever
depends on these protocols.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from dataclasses import dataclass, field

from ..domain import Course, Event, Grade, Lesson, Note, Task, TaskKind


class CourseRepository(Protocol):
    def list(self) -> list[Course]: ...
    def get(self, course_id: int) -> Course | None: ...
    def add(self, course: Course) -> int: ...
    def update(self, course: Course) -> None: ...
    def delete(self, course_id: int) -> None: ...


class EventRepository(Protocol):
    def between(self, first: date, last: date) -> list[Event]: ...
    def get(self, event_id: int) -> Event | None: ...
    def add(self, event: Event) -> int: ...
    def update(self, event: Event) -> None: ...
    def delete(self, event_id: int) -> None: ...


class TaskRepository(Protocol):
    def list(self, include_done: bool = True, course_id: int | None = None) -> list[Task]: ...
    def by_external_prefix(self, prefix: str) -> list[Task]: ...
    def due_on(self, day: date) -> list[Task]: ...
    def open_due_before(self, day: date) -> list[Task]: ...
    def get(self, task_id: int) -> Task | None: ...
    def add(self, task: Task) -> int: ...
    def update(self, task: Task) -> None: ...
    def delete(self, task_id: int) -> None: ...


class NoteRepository(Protocol):
    def search(self, text: str = "", course_id: int | None = None) -> list[Note]: ...
    def find_by_title(self, title: str, course_id: int | None) -> Note | None: ...
    def topics(self, course_id: int | None) -> list[str]: ...
    def rename_topic(self, course_id: int | None, old: str, new: str) -> int: ...
    def get(self, note_id: int) -> Note | None: ...
    def add(self, note: Note) -> int: ...
    def update(self, note: Note) -> None: ...
    def delete(self, note_id: int) -> None: ...


class JournalRepository(Protocol):
    def get(self, day: date) -> str: ...
    def put(self, day: date, body: str) -> None: ...


class Storage(Protocol):
    @property
    def location(self) -> Path: ...
    def backup_to(self, dest: Path) -> None: ...


class Clock(Protocol):
    def today(self) -> date: ...
    def now(self) -> datetime: ...


class KeyValueStore(Protocol):
    """Small persistent settings, e.g. when the last sync happened."""

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str | None) -> None: ...


class SchoolRecordRepository(Protocol):
    """Grades and lesson topics mirrored from the school register."""

    def grades(self) -> list[Grade]: ...
    def replace_grades(self, grades: list[Grade]) -> None: ...
    def lessons_between(self, first: date, last: date) -> list[Lesson]: ...
    def replace_lessons(self, first: date, last: date, lessons: list[Lesson]) -> None: ...


# ---- school register (e.g. Classeviva) ----------------------------------------

@dataclass(frozen=True)
class Credentials:
    username: str
    password: str


class CredentialStore(Protocol):
    """Somewhere safe to keep the register password (e.g. the OS keyring)."""

    def load(self) -> Credentials | None: ...
    def save(self, credentials: Credentials) -> None: ...
    def clear(self) -> None: ...


@dataclass(frozen=True)
class RemoteSubject:
    id: str
    name: str
    teachers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RemoteAssignment:
    """Homework, a test or a note a teacher put on the register's agenda."""

    id: str
    day: date
    kind: TaskKind
    text: str
    subject_id: str | None = None
    subject_name: str = ""
    author: str = ""


@dataclass(frozen=True)
class RemoteGrade:
    id: str
    day: date
    subject_id: str | None
    subject_name: str
    display: str
    value: float | None
    component: str = ""
    period: str = ""
    notes: str = ""
    cancelled: bool = False


@dataclass(frozen=True)
class RemoteLesson:
    id: str
    day: date
    subject_id: str | None
    subject_name: str
    topic: str
    teacher: str = ""
    hour: int = 0


@dataclass(frozen=True)
class RegisterAccount:
    student_name: str


@dataclass(frozen=True)
class RegisterSnapshot:
    """Everything fetched in one sync, before it touches local storage."""

    account: RegisterAccount
    subjects: tuple[RemoteSubject, ...] = ()
    assignments: tuple[RemoteAssignment, ...] = ()
    grades: tuple[RemoteGrade, ...] = ()
    lessons: tuple[RemoteLesson, ...] = ()
    assignment_window: tuple[date, date] | None = None
    lesson_window: tuple[date, date] | None = None


class SchoolRegister(Protocol):
    """A school's electronic register. Implementations do network I/O only."""

    name: str  # shown to the user, e.g. "Classeviva"

    def login(self, credentials: Credentials) -> RegisterAccount: ...
    def subjects(self) -> list[RemoteSubject]: ...
    def assignments(self, first: date, last: date) -> list[RemoteAssignment]: ...
    def grades(self) -> list[RemoteGrade]: ...
    def lessons(self, first: date, last: date) -> list[RemoteLesson]: ...
