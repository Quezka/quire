"""Interfaces the application needs from the outside world.

Infrastructure provides the implementations; the application only ever
depends on these protocols.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from dataclasses import dataclass

from ..domain import (
    Course, Event, FocusSession, Grade, Job, Lesson, Note, Shift, Subject, Task, TaskKind,
)


class CourseRepository(Protocol):
    def list(self) -> list[Course]: ...
    def get(self, course_id: int) -> Course | None: ...
    def add(self, course: Course) -> int: ...
    def update(self, course: Course) -> None: ...
    def delete(self, course_id: int) -> None: ...
    def merge_into(self, source_id: int, target_id: int) -> None:
        """Move every task, note, grade and lesson of `source` to `target`, then delete it."""
        ...


class EventRepository(Protocol):
    def between(self, first: date, last: date) -> list[Event]: ...
    def get(self, event_id: int) -> Event | None: ...
    def add(self, event: Event) -> int: ...
    def update(self, event: Event) -> None: ...
    def delete(self, event_id: int) -> None: ...


class JobRepository(Protocol):
    """Jobs are loaded and saved together with their weekly schedule."""

    def list(self) -> list[Job]: ...
    def get(self, job_id: int) -> Job | None: ...
    def add(self, job: Job) -> int: ...
    def update(self, job: Job) -> None: ...
    def delete(self, job_id: int) -> None: ...


class ShiftRepository(Protocol):
    def starting_between(self, first: date, last: date) -> list[Shift]: ...
    def skipped(self, first: date, last: date) -> set[tuple[int, date, int]]:
        """Weekly-schedule occurrences the user skipped, as (job id, day, start)."""
        ...
    def skip(self, job_id: int, day: date, start: int) -> None: ...
    def get(self, shift_id: int) -> Shift | None: ...
    def add(self, shift: Shift) -> int: ...
    def update(self, shift: Shift) -> None: ...
    def delete(self, shift_id: int) -> None: ...


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


class FocusLogRepository(Protocol):
    def add(self, session: FocusSession) -> None: ...
    def between(self, first: date, last: date) -> list[FocusSession]: ...
    def recent_labels(self, limit: int) -> list[str]:
        """Ad-hoc projects (sessions without a task), most recently used first."""
        ...


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
    def subjects(self) -> list[Subject]: ...
    def replace_subjects(self, subjects: list[Subject]) -> None: ...


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
    # Where it came from. The "agenda" feed is complete for the dates asked for, so
    # anything missing from it was deleted; the "homework" feed only lists current
    # items, so missing ones are kept.
    feed: str = "agenda"
    done: bool = False  # already marked done on the register


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
    """Everything fetched in one sync, before it touches local storage.

    A part that couldn't be fetched is None (not empty), so applying the snapshot
    leaves the local copy of that part alone; `problems` says what went wrong.
    """

    account: RegisterAccount
    subjects: tuple[RemoteSubject, ...] | None = ()
    assignments: tuple[RemoteAssignment, ...] | None = ()
    homework: tuple[RemoteAssignment, ...] | None = ()
    grades: tuple[RemoteGrade, ...] | None = ()
    lessons: tuple[RemoteLesson, ...] | None = ()
    assignment_window: tuple[date, date] | None = None
    lesson_window: tuple[date, date] | None = None
    problems: tuple[str, ...] = ()


class SchoolRegister(Protocol):
    """A school's electronic register. Implementations do network I/O only."""

    name: str  # shown to the user, e.g. "Classeviva"

    def login(self, credentials: Credentials) -> RegisterAccount: ...
    def subjects(self) -> list[RemoteSubject]: ...
    def assignments(self, first: date, last: date) -> list[RemoteAssignment]: ...
    def homework(self) -> list[RemoteAssignment]:
        """Homework set through the register's homework feature, if it has one."""
        ...
    def grades(self) -> list[RemoteGrade]: ...
    def lessons(self, first: date, last: date) -> list[RemoteLesson]: ...


# ---- sync between devices -------------------------------------------------------

@dataclass(frozen=True)
class SyncRecord:
    """One synced thing (a course with its class times, a task, a note, …) in a form every
    device understands: stable ids instead of local row numbers.

    `modified` is an ISO-8601 UTC time with milliseconds; the newer change wins.
    """

    kind: str  # "course", "event", "task", "note", "journal", "job", "shift", "focus"
    uid: str
    modified: str
    deleted: bool = False
    data: dict | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.kind, self.uid


class SyncStore(Protocol):
    """This device's side of sync: what changed here, and applying what changed elsewhere."""

    def outgoing(self) -> list[SyncRecord]:
        """Every record changed (or deleted) here since it was last sent."""
        ...

    def apply(self, records: list[SyncRecord]) -> set[tuple[str, str]]:
        """Take in records from other devices where they're newer than ours; returns the
        (kind, uid) of those applied. Records whose parent hasn't arrived yet wait for the
        next sync."""
        ...

    def mark_sent(self, records: list[SyncRecord]) -> None:
        """They reached the cloud: stop sending them, unless they changed again since."""
        ...

    def pending(self) -> int: ...

    def clear_all(self) -> None:
        """Delete every synced record here without sending deletions (to take the cloud's copy)."""
        ...


@dataclass(frozen=True)
class CloudConfig:
    project_id: str
    api_key: str


@dataclass(frozen=True)
class CloudSession:
    user_id: str
    email: str
    token: str  # short-lived
    refresh_token: str  # long-lived; kept in the keyring


class CloudBackend(Protocol):
    """A cloud database with accounts (e.g. Firebase). Network only: safe on a worker thread."""

    def sign_up(self, config: CloudConfig, email: str, password: str) -> CloudSession: ...
    def sign_in(self, config: CloudConfig, email: str, password: str) -> CloudSession: ...
    def refresh(self, config: CloudConfig, refresh_token: str) -> CloudSession: ...

    def pull(self, config: CloudConfig, session: CloudSession,
             cursor: str | None) -> tuple[list[SyncRecord], str | None]:
        """Records that reached the cloud after `cursor` (None: all), and the new cursor."""
        ...

    def push(self, config: CloudConfig, session: CloudSession,
             records: list[SyncRecord]) -> None: ...
