"""Enterprise business rules: entities and invariants, free of any framework."""
from .errors import DomainError, NotFound, ValidationError
from .focus import FocusSession, FocusSettings, Phase, PhaseEnded, PomodoroTimer
from .model import (
    COURSE_COLORS, EVERY_DAY, PASS_MARK, UPCOMING_DAYS, WORK_DAYS, ClassSlot, Course, DueBucket, Event, Grade, Job, Lesson, Note,
    Shift, ShiftPattern, Subject, Task, TaskKind, TimeRange, average, derive_note_title,
    net_pay, normalize_topic, reschedule, work_shifts,
)
from .register import (
    ABSENCE_LIMIT, GRADE_MAX, GRADE_MIN, Absence, AbsenceKind, Book, DocumentKind, Notice,
    NoticeAttachment, SchoolDocument, lesson_hours, needed_grade, running_average,
)

__all__ = [
    "FocusSession", "FocusSettings", "Phase", "PhaseEnded", "PomodoroTimer",
    "DomainError", "NotFound", "ValidationError", "COURSE_COLORS", "EVERY_DAY", "PASS_MARK", "UPCOMING_DAYS", "WORK_DAYS", "ClassSlot", "Course",
    "DueBucket", "Event", "Grade", "Job", "Lesson", "Note", "Shift", "ShiftPattern", "Subject", "Task", "TaskKind", "TimeRange", "average",
    "derive_note_title", "net_pay", "normalize_topic", "reschedule", "work_shifts",
    "ABSENCE_LIMIT", "GRADE_MAX", "GRADE_MIN", "Absence", "AbsenceKind", "Book", "DocumentKind",
    "Notice", "NoticeAttachment", "SchoolDocument", "lesson_hours", "needed_grade",
    "running_average",
]
