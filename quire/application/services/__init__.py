from __future__ import annotations

from dataclasses import dataclass

from ..bus import ChangeBus
from ..ports import Storage
from .focus import FocusService, FocusStats
from .notes import NoteService
from .planner import PlannerService
from .reminders import Reminder, ReminderService, ReminderSettings
from .school import SchoolSyncService
from .school_records import SchoolRecordsService
from .startup import StartupService
from .sync import SyncResult, SyncService, SyncStatus
from .tasks import TaskService
from .timetable import TimetableService
from .updates import AvailableUpdate, UpdateService
from .work import WorkService


@dataclass(frozen=True)
class Services:
    """Everything the presentation layer is allowed to talk to."""

    timetable: TimetableService
    planner: PlannerService
    tasks: TaskService
    notes: NoteService
    school: SchoolRecordsService  # grades, homework, lessons: what's been synced
    school_sync: SchoolSyncService  # the register account and syncing
    work: WorkService
    focus: FocusService
    reminders: ReminderService
    sync: SyncService  # between your devices, through a cloud account
    updates: UpdateService  # new versions of Quire itself
    startup: StartupService  # background running and starting at login
    storage: Storage
    bus: ChangeBus


__all__ = ["Services", "FocusService", "FocusStats", "NoteService", "PlannerService", "Reminder", "ReminderService", "ReminderSettings", "SchoolRecordsService", "SchoolSyncService", "StartupService", "SyncResult", "SyncService", "SyncStatus", "TaskService",
           "TimetableService", "AvailableUpdate", "UpdateService", "WorkService"]
