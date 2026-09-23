from __future__ import annotations

from dataclasses import dataclass

from ..bus import ChangeBus
from ..ports import Storage
from .notes import NoteService
from .planner import PlannerService
from .school import SchoolSyncService
from .tasks import TaskService
from .timetable import TimetableService
from .work import WorkService


@dataclass(frozen=True)
class Services:
    """Everything the presentation layer is allowed to talk to."""

    timetable: TimetableService
    planner: PlannerService
    tasks: TaskService
    notes: NoteService
    school: SchoolSyncService
    work: WorkService
    storage: Storage
    bus: ChangeBus


__all__ = ["Services", "NoteService", "PlannerService", "SchoolSyncService", "TaskService",
           "TimetableService", "WorkService"]
