"""Composition root: the only module that knows every layer and wires them together."""
from __future__ import annotations

from pathlib import Path

from .application.bus import ChangeBus
from .application.ports import Clock, CredentialStore, SchoolRegister
from .application.services import (
    FocusService, NoteService, PlannerService, SchoolSyncService, Services, TaskService,
    TimetableService, WorkService,
)
from .infrastructure.classeviva import ClassevivaRegister
from .infrastructure.clock import SystemClock
from .infrastructure.credentials import KeyringCredentialStore
from .infrastructure.repositories import (
    SqliteCourseRepository, SqliteEventRepository, SqliteFocusLogRepository, SqliteJobRepository,
    SqliteJournalRepository,
    SqliteKeyValueStore, SqliteNoteRepository, SqliteSchoolRecordRepository,
    SqliteShiftRepository, SqliteTaskRepository,
)
from .infrastructure.sqlite import SqliteDatabase


def build_services(db_path: str | Path, clock: Clock | None = None,
                   register: SchoolRegister | None = None,
                   credentials: CredentialStore | None = None,
                   ) -> tuple[Services, SqliteDatabase]:
    db = SqliteDatabase(db_path)
    clock = clock or SystemClock()
    bus = ChangeBus()
    courses = SqliteCourseRepository(db)
    events = SqliteEventRepository(db)
    tasks = SqliteTaskRepository(db)
    notes = SqliteNoteRepository(db)
    journal = SqliteJournalRepository(db)
    jobs = SqliteJobRepository(db)
    shifts = SqliteShiftRepository(db)
    settings = SqliteKeyValueStore(db)
    services = Services(
        timetable=TimetableService(courses, bus),
        planner=PlannerService(courses, events, tasks, journal, clock, bus, jobs, shifts),
        tasks=TaskService(tasks, courses, clock, bus),
        notes=NoteService(notes, courses, clock, bus),
        school=SchoolSyncService(
            register or ClassevivaRegister(), credentials or KeyringCredentialStore(),
            courses, tasks, SqliteSchoolRecordRepository(db), settings, clock, bus),
        work=WorkService(jobs, shifts, clock, bus),
        focus=FocusService(SqliteFocusLogRepository(db), settings, tasks, courses, clock, bus),
        storage=db,
        bus=bus,
    )
    return services, db
