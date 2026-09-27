"""Composition root: the only module that knows every layer and wires them together."""
from __future__ import annotations

from pathlib import Path

from .application.bus import ChangeBus
from .application.ports import CloudBackend, Clock, CredentialStore, SchoolRegister
from .application.services import (
    FocusService, NoteService, PlannerService, ReminderService, SchoolRecordsService,
    SchoolSyncService, Services, SyncService, TaskService, TimetableService, WorkService,
)
from .infrastructure.classeviva import ClassevivaRegister
from .infrastructure.clock import SystemClock
from .infrastructure.credentials import KeyringCredentialStore
from .infrastructure.firebase import FirebaseCloud
from .infrastructure.repositories import (
    SqliteCourseRepository, SqliteEventRepository, SqliteFocusLogRepository, SqliteJobRepository,
    SqliteJournalRepository,
    SqliteKeyValueStore, SqliteNoteRepository, SqliteSchoolRecordRepository,
    SqliteShiftRepository, SqliteTaskRepository,
)
from .infrastructure.sqlite import SqliteDatabase
from .infrastructure.sync_store import SqliteSyncStore


def build_services(db_path: str | Path, clock: Clock | None = None,
                   register: SchoolRegister | None = None,
                   credentials: CredentialStore | None = None,
                   cloud: CloudBackend | None = None,
                   sync_secrets: CredentialStore | None = None,
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
    records = SqliteSchoolRecordRepository(db)
    register = register or ClassevivaRegister()
    planner = PlannerService(courses, events, tasks, journal, clock, bus, jobs, shifts)
    services = Services(
        timetable=TimetableService(courses, bus),
        planner=planner,
        tasks=TaskService(tasks, courses, clock, bus),
        notes=NoteService(notes, courses, clock, bus),
        school=SchoolRecordsService(courses, tasks, records, clock, register.name.lower()),
        school_sync=SchoolSyncService(register, credentials or KeyringCredentialStore(),
                                      courses, tasks, records, settings, clock, bus),
        work=WorkService(jobs, shifts, clock, bus),
        focus=FocusService(SqliteFocusLogRepository(db), settings, tasks, courses, clock, bus),
        reminders=ReminderService(planner, settings, clock),
        sync=SyncService(SqliteSyncStore(db), cloud or FirebaseCloud(),
                         sync_secrets or KeyringCredentialStore("sync"), settings, clock, bus),
        storage=db,
        bus=bus,
    )
    return services, db
